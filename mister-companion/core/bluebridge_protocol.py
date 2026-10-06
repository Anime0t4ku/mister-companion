import base64
import json
import os
import re
import struct
import threading
import time
from core.bluebridge_releases import version_key, bluebridge_release, download_bluebridge_release

def _version_tuple(value):
    return version_key(value)

BLUEBRIDGE_UF2_FAMILIES = {0xE48BFF57, 0xE48BFF59, 0xE48BFF5B}
BLUEBRIDGE_UF2_CODE_FAMILIES = {0xE48BFF59, 0xE48BFF5B}

def _uf2_info(data):
    if not data or len(data) % 512:
        raise ValueError("Invalid UF2 file size")
    chunks = []
    families = set()
    seen_blocks = set()
    block_groups = {}
    for offset in range(0, len(data), 512):
        block = data[offset:offset + 512]
        magic0, magic1, flags, target, payload_size, block_no, num_blocks, family = struct.unpack_from("<IIIIIIII", block, 0)
        magic_end = struct.unpack_from("<I", block, 508)[0]
        if magic0 != 0x0A324655 or magic1 != 0x9E5D5157 or magic_end != 0x0AB16F30:
            raise ValueError("Invalid UF2 block")
        if payload_size == 0 or payload_size > 476:
            raise ValueError("Invalid UF2 payload")
        family_id = family if flags & 0x00002000 else 0
        key = (family_id, num_blocks, block_no)
        if key in seen_blocks:
            raise ValueError("Duplicate UF2 block")
        seen_blocks.add(key)
        if not num_blocks or block_no >= num_blocks:
            raise ValueError("Invalid UF2 block sequence")
        compatibility_block = (
            offset == 0 and family_id == 0xE48BFF57 and
            flags in (0x00002000, 0x0000A000) and payload_size == 256 and
            block_no == 0 and num_blocks == 2 and
            0x10000000 <= target < 0x12000000 and target % 256 == 0 and
            block[32:288] == b'\xef' * 256 and
            (not flags & 0x00008000 or struct.unpack_from("<I", block, 288)[0] == 0x9957E304)
        )
        if compatibility_block:
            continue
        block_groups.setdefault((family_id, num_blocks), set()).add(block_no)
        if family_id:
            families.add(family_id)
            if family_id not in BLUEBRIDGE_UF2_FAMILIES:
                raise ValueError("This UF2 contains blocks for an unsupported device family")
        if family_id in BLUEBRIDGE_UF2_FAMILIES:
            chunks.append((target, block[32:32 + payload_size]))
    if not block_groups:
        raise ValueError("UF2 contains no firmware blocks")
    firmware_blocks = sum(len(numbers) for numbers in block_groups.values())
    complete_per_family = all(len(numbers) == count for (_, count), numbers in block_groups.items())
    counts = {count for _, count in block_groups}
    global_numbers = {number for numbers in block_groups.values() for number in numbers}
    complete_global = len(counts) == 1 and next(iter(counts)) == firmware_blocks and len(global_numbers) == firmware_blocks
    if not complete_per_family and not complete_global:
        raise ValueError("Incomplete UF2 block sequence")
    if not families.intersection(BLUEBRIDGE_UF2_CODE_FAMILIES):
        raise ValueError("This UF2 is not for MC BlueBridge on Raspberry Pi Pico 2 W")
    image = b"".join(payload for _, payload in sorted(chunks, key=lambda item: item[0]))
    match = re.search(rb"MCBLUEBRIDGE\|([0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?)\|PICO2W\|SCHEMA=([0-9]+)", image)
    version = None
    schema = None
    if match:
        version = match.group(1).decode("ascii")
        schema = int(match.group(2))
    elif b"MC BlueBridge" in image:
        versions = [x.decode("ascii") for x in re.findall(rb"(?<![0-9])[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?![0-9])", image)]
        if versions:
            version = max(versions, key=_version_tuple)
    if not version:
        raise ValueError("Unable to identify this file as MC BlueBridge firmware")
    return {"version": version, "config_schema": schema, "family": "RP2350", "size": len(data)}

def _inspect_bluebridge_firmware(data, bluebridge):
    info = _uf2_info(data)
    current = bluebridge.status()
    if not current.get("detected"):
        raise RuntimeError("MC BlueBridge not detected")
    current_version = str(current.get("firmware", "0.0.0"))
    a = _version_tuple(info["version"])
    b = _version_tuple(current_version)
    relation = "newer" if a > b else "same" if a == b else "older"
    info["current_version"] = current_version
    info["relation"] = relation
    return info

class BlueBridgeManager:
    def __init__(self, adapter_id=None):
        self.lock = threading.RLock()
        self.adapter_id = adapter_id
        self.adapter_name = "MC BlueBridge adapter"
        self.verified = False
        self.path = None
        self.fd = None
        self.rx = b""
        self.counter = 0
        self.info = {}


    def _next_id(self):
        self.counter = (self.counter + 1) & 0x7fffffff
        if self.counter == 0:
            self.counter = 1
        return str(self.counter)


    def _send(self, command, *args):
        self.connect()
        request_id = self._next_id()
        fields = ["BB1", request_id, command]
        fields.extend(str(x).replace("\r", " ").replace("\n", " ") for x in args)
        self._write("|".join(fields) + "\n")
        return request_id


    def _parse_line(self, line):
        parts = line.split("|", 3)
        if len(parts) < 3 or parts[0] != "BB1":
            return None
        return parts[1], parts[2], parts[3] if len(parts) > 3 else ""


    def request(self, command, *args, timeout=2.5):
        with self.lock:
            try:
                request_id = self._send(command, *args)
                end = time.monotonic() + timeout
                while time.monotonic() < end:
                    parsed = self._parse_line(self._readline(max(0.05, end - time.monotonic())))
                    if not parsed or parsed[0] != request_id:
                        continue
                    _, status, payload = parsed
                    if status == "ERR":
                        raise RuntimeError(payload or "BlueBridge command failed")
                    if status != "OK":
                        raise RuntimeError("Unexpected BlueBridge response")
                    return payload
                raise TimeoutError("BlueBridge did not respond")
            except Exception:
                self.close()
                raise


    def request_json(self, command, *args, timeout=2.5):
        payload = self.request(command, *args, timeout=timeout)
        if not payload:
            return {}
        try:
            return json.loads(payload)
        except Exception:
            return {"value": payload}


    def status(self):
        try:
            hello = self.request_json("HELLO")
            status = self.request_json("STATUS")
            status["detected"] = True
            status["port"] = self.path
            status["serial"] = self.info.get("serial", "")
            status["usb_product"] = self.info.get("product", "")
            status["protocol"] = hello.get("protocol", status.get("protocol"))
            status["config_schema"] = hello.get("config_schema")
            status["capabilities"] = hello.get("capabilities", {})
            self.adapter_name = hello.get("adapter_name") or "MC BlueBridge adapter"
            status["adapter_id"] = self.adapter_id
            status["adapter_name"] = self.adapter_name
            status["adapter_custom_name"] = hello.get("adapter_custom_name", "")
            return status
        except Exception as e:
            return {"detected": False, "connected": False, "message": str(e)}


    def controllers(self):
        return self.request_json("CONTROLLERS")


    def profiles(self):
        return self.request_json("PROFILES")


    def profile(self, index):
        return self.request_json("PROFILE_GET", int(index))


    def export_config(self):
        with self.lock:
            try:
                request_id = self._send("CONFIG_EXPORT")
                schema = None
                size = None
                checksum = None
                chunks = {}
                ended = False
                end = time.monotonic() + 8.0
                while time.monotonic() < end:
                    parsed = self._parse_line(self._readline(max(0.05, end - time.monotonic())))
                    if not parsed or parsed[0] != request_id:
                        continue
                    _, status, payload = parsed
                    if status == "ERR":
                        raise RuntimeError(payload or "BlueBridge export failed")
                    if status == "DATA_BEGIN":
                        fields = payload.split("|")
                        if len(fields) != 3:
                            raise RuntimeError("Invalid BlueBridge export header")
                        schema = int(fields[0])
                        size = int(fields[1])
                        checksum = int(fields[2])
                    elif status == "DATA":
                        fields = payload.split("|", 1)
                        if len(fields) != 2:
                            raise RuntimeError("Invalid BlueBridge export chunk")
                        chunks[int(fields[0])] = fields[1]
                    elif status == "DATA_END":
                        ended = True
                        break
                if not ended or schema is None or size is None or checksum is None:
                    raise RuntimeError("Incomplete BlueBridge export")
                data = bytearray(size)
                written = 0
                for offset in sorted(chunks):
                    raw = bytes.fromhex(chunks[offset])
                    end_offset = offset + len(raw)
                    if offset != written or end_offset > size:
                        raise RuntimeError("Invalid BlueBridge export data")
                    data[offset:end_offset] = raw
                    written = end_offset
                if written != size:
                    raise RuntimeError("Incomplete BlueBridge export data")
                return {
                    "format": "MC-BLUEBRIDGE-CONFIG-1",
                    "schema": schema,
                    "size": size,
                    "checksum": checksum,
                    "data": base64.b64encode(bytes(data)).decode("ascii"),
                }
            except Exception:
                self.close()
                raise


    def import_config(self, package):
        if str(package.get("format", "")) != "MC-BLUEBRIDGE-CONFIG-1":
            raise ValueError("Unsupported BlueBridge configuration file")
        schema = int(package.get("schema", 0))
        size = int(package.get("size", 0))
        checksum = int(package.get("checksum", 0))
        try:
            data = base64.b64decode(str(package.get("data", "")), validate=True)
        except Exception:
            raise ValueError("Invalid BlueBridge configuration data")
        if len(data) != size:
            raise ValueError("BlueBridge configuration size does not match")
        self.request("CONFIG_IMPORT_BEGIN", schema, size, checksum, timeout=3.0)
        chunk_size = 128
        for offset in range(0, len(data), chunk_size):
            self.request("CONFIG_IMPORT_CHUNK", offset, data[offset:offset + chunk_size].hex().upper(), timeout=3.0)
        self.request("CONFIG_IMPORT_COMMIT", timeout=4.0)
        return True


