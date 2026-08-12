from __future__ import annotations

import hashlib
import struct
import zlib
from pathlib import Path

SUPPORTED_PATCH_FORMATS = ("IPS", "IPS32", "BPS", "UPS", "PPF")
SUPPORTED_PATCH_EXTENSIONS = (".ips", ".ips32", ".bps", ".ups", ".ppf")


class PatchError(RuntimeError):
    pass


def _u16be(data: bytes, pos: int) -> tuple[int, int]:
    if pos + 2 > len(data):
        raise PatchError("Unexpected end of patch.")
    return int.from_bytes(data[pos:pos + 2], "big"), pos + 2


def _u24be(data: bytes, pos: int) -> tuple[int, int]:
    if pos + 3 > len(data):
        raise PatchError("Unexpected end of patch.")
    return int.from_bytes(data[pos:pos + 3], "big"), pos + 3


def _vlv(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    shift = 1
    while True:
        if pos >= len(data):
            raise PatchError("Unexpected end of patch while reading a variable-length value.")
        x = data[pos]
        pos += 1
        value += (x & 0x7F) * shift
        if x & 0x80:
            return value, pos
        shift <<= 7
        value += shift


def detect_patch_format(patch: bytes | str | Path) -> str:
    data = Path(patch).read_bytes() if isinstance(patch, (str, Path)) else bytes(patch)
    if data.startswith(b"PATCH"):
        return "IPS"
    if data.startswith(b"IPS32"):
        return "IPS32"
    if data.startswith(b"BPS1"):
        return "BPS"
    if data.startswith(b"UPS1"):
        return "UPS"
    if data.startswith((b"PPF10", b"PPF20", b"PPF30")):
        return "PPF"
    raise PatchError("Unsupported patch format. Supported formats: IPS, IPS32, BPS, UPS and PPF.")


def checksum_info(path: str | Path) -> dict[str, str]:
    path = Path(path)
    crc = 0
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            crc = zlib.crc32(chunk, crc)
            md5.update(chunk)
            sha1.update(chunk)
    return {
        "CRC32": f"{crc & 0xFFFFFFFF:08X}",
        "MD5": md5.hexdigest().upper(),
        "SHA1": sha1.hexdigest().upper(),
    }


def validation_label(patch_format: str) -> str:
    return "CRC32 source verification" if patch_format in {"BPS", "UPS"} else "No embedded source checksum"


def _apply_ips(source: bytes, patch: bytes, ips32: bool = False) -> bytes:
    magic = b"IPS32" if ips32 else b"PATCH"
    if not patch.startswith(magic):
        raise PatchError(f"Invalid {'IPS32' if ips32 else 'IPS'} patch header.")
    pos = len(magic)
    out = bytearray(source)
    eof = b"EEOF" if ips32 else b"EOF"
    offset_size = 4 if ips32 else 3

    while True:
        if pos + len(eof) <= len(patch) and patch[pos:pos + len(eof)] == eof:
            pos += len(eof)
            break
        if pos + offset_size > len(patch):
            raise PatchError("IPS patch is missing its EOF marker.")
        offset = int.from_bytes(patch[pos:pos + offset_size], "big")
        pos += offset_size
        length, pos = _u16be(patch, pos)
        if length == 0:
            run_length, pos = _u16be(patch, pos)
            if pos >= len(patch):
                raise PatchError("Invalid IPS RLE record.")
            payload = bytes([patch[pos]]) * run_length
            pos += 1
        else:
            if pos + length > len(patch):
                raise PatchError("Invalid IPS record length.")
            payload = patch[pos:pos + length]
            pos += length
        end = offset + len(payload)
        if end > len(out):
            out.extend(b"\x00" * (end - len(out)))
        out[offset:end] = payload

    truncate_size = 4 if ips32 else 3
    if pos + truncate_size == len(patch):
        new_size = int.from_bytes(patch[pos:pos + truncate_size], "big")
        if new_size < len(out):
            del out[new_size:]
        elif new_size > len(out):
            out.extend(b"\x00" * (new_size - len(out)))
    return bytes(out)


def _apply_bps(source: bytes, patch: bytes) -> bytes:
    if not patch.startswith(b"BPS1") or len(patch) < 16:
        raise PatchError("Invalid BPS patch.")
    expected_patch_crc = int.from_bytes(patch[-4:], "little")
    if zlib.crc32(patch[:-4]) & 0xFFFFFFFF != expected_patch_crc:
        raise PatchError("BPS patch checksum mismatch.")

    pos = 4
    source_size, pos = _vlv(patch, pos)
    target_size, pos = _vlv(patch, pos)
    metadata_size, pos = _vlv(patch, pos)
    pos += metadata_size
    if pos > len(patch) - 12:
        raise PatchError("Invalid BPS metadata length.")

    source_crc = int.from_bytes(patch[-12:-8], "little")
    target_crc = int.from_bytes(patch[-8:-4], "little")
    if source_size != len(source):
        raise PatchError(f"BPS source size mismatch (expected {source_size}, got {len(source)}).")
    if zlib.crc32(source) & 0xFFFFFFFF != source_crc:
        raise PatchError("BPS source ROM checksum mismatch. This patch expects a different source ROM.")

    out = bytearray()
    source_relative = 0
    target_relative = 0
    end_actions = len(patch) - 12
    while pos < end_actions:
        action, pos = _vlv(patch, pos)
        mode = action & 3
        length = (action >> 2) + 1
        if mode == 0:  # SourceRead: same offset as current target position
            start = len(out)
            end = start + length
            if end > len(source):
                raise PatchError("BPS SourceRead exceeds source ROM size.")
            out.extend(source[start:end])
        elif mode == 1:  # TargetRead
            if pos + length > end_actions:
                raise PatchError("BPS TargetRead exceeds patch data.")
            out.extend(patch[pos:pos + length])
            pos += length
        elif mode == 2:  # SourceCopy
            encoded, pos = _vlv(patch, pos)
            source_relative += -(encoded >> 1) if encoded & 1 else (encoded >> 1)
            if source_relative < 0 or source_relative + length > len(source):
                raise PatchError("BPS SourceCopy exceeds source ROM size.")
            out.extend(source[source_relative:source_relative + length])
            source_relative += length
        else:  # TargetCopy; overlap is intentional
            encoded, pos = _vlv(patch, pos)
            target_relative += -(encoded >> 1) if encoded & 1 else (encoded >> 1)
            if target_relative < 0:
                raise PatchError("Invalid BPS TargetCopy offset.")
            for _ in range(length):
                if target_relative >= len(out):
                    raise PatchError("BPS TargetCopy references data that has not been written yet.")
                out.append(out[target_relative])
                target_relative += 1

    if len(out) != target_size:
        raise PatchError(f"BPS target size mismatch (expected {target_size}, got {len(out)}).")
    if zlib.crc32(out) & 0xFFFFFFFF != target_crc:
        raise PatchError("BPS target checksum mismatch after patching.")
    return bytes(out)


def _apply_ups(source: bytes, patch: bytes) -> bytes:
    if not patch.startswith(b"UPS1") or len(patch) < 16:
        raise PatchError("Invalid UPS patch.")
    expected_patch_crc = int.from_bytes(patch[-4:], "little")
    if zlib.crc32(patch[:-4]) & 0xFFFFFFFF != expected_patch_crc:
        raise PatchError("UPS patch checksum mismatch.")

    pos = 4
    source_size, pos = _vlv(patch, pos)
    target_size, pos = _vlv(patch, pos)
    source_crc = int.from_bytes(patch[-12:-8], "little")
    target_crc = int.from_bytes(patch[-8:-4], "little")
    if source_size != len(source):
        raise PatchError(f"UPS source size mismatch (expected {source_size}, got {len(source)}).")
    if zlib.crc32(source) & 0xFFFFFFFF != source_crc:
        raise PatchError("UPS source ROM checksum mismatch. This patch expects a different source ROM.")

    out = bytearray(target_size)
    out[:min(len(source), target_size)] = source[:min(len(source), target_size)]
    source_cursor = 0
    target_cursor = 0
    end_records = len(patch) - 12
    while pos < end_records:
        relative, pos = _vlv(patch, pos)
        source_cursor += relative
        target_cursor += relative
        while True:
            if pos >= end_records:
                raise PatchError("Invalid UPS XOR record.")
            value = patch[pos]
            pos += 1
            if value == 0:
                source_cursor += 1
                target_cursor += 1
                break
            source_byte = source[source_cursor] if source_cursor < len(source) else 0
            if target_cursor >= len(out):
                raise PatchError("UPS record exceeds target ROM size.")
            out[target_cursor] = source_byte ^ value
            source_cursor += 1
            target_cursor += 1

    if zlib.crc32(out) & 0xFFFFFFFF != target_crc:
        raise PatchError("UPS target checksum mismatch after patching.")
    return bytes(out)


def _apply_ppf(source: bytes, patch: bytes) -> bytes:
    if len(patch) < 56 or patch[:3] != b"PPF":
        raise PatchError("Invalid PPF patch.")
    try:
        version = int(patch[3:5].decode("ascii")) / 10
    except Exception as exc:
        raise PatchError("Invalid PPF version.") from exc
    version_marker = patch[5] + 1
    if version not in {1.0, 2.0, 3.0} or int(version) != version_marker:
        raise PatchError("Invalid or unsupported PPF version.")

    pos = 56
    block_check = False
    undo_data = False
    if version == 3.0:
        if pos + 4 > len(patch):
            raise PatchError("Invalid PPF3 header.")
        _image_type = patch[pos]
        block_check = bool(patch[pos + 1])
        undo_data = bool(patch[pos + 2])
        pos += 4
    elif version == 2.0:
        block_check = True
        if pos + 4 > len(patch):
            raise PatchError("Invalid PPF2 header.")
        _expected_size = int.from_bytes(patch[pos:pos + 4], "little")
        pos += 4

    if block_check:
        if pos + 1024 > len(patch):
            raise PatchError("Invalid PPF block-check data.")
        pos += 1024

    out = bytearray(source)
    while pos < len(patch):
        if patch[pos:pos + 4] == b"@BEG":
            break
        offset_size = 8 if version == 3.0 else 4
        if pos + offset_size + 1 > len(patch):
            break
        offset = int.from_bytes(patch[pos:pos + offset_size], "little")
        pos += offset_size
        length = patch[pos]
        pos += 1
        if pos + length > len(patch):
            raise PatchError("Invalid PPF record length.")
        new_data = patch[pos:pos + length]
        pos += length
        undo = b""
        if undo_data:
            if pos + length > len(patch):
                raise PatchError("Invalid PPF undo record.")
            undo = patch[pos:pos + length]
            pos += length
        end = offset + length
        if end > len(out):
            out.extend(b"\x00" * (end - len(out)))
        # PPF3 can contain undo bytes. Apply forward data unless the image already
        # contains the forward bytes, in which case mirror PPF-O-Matic behavior and undo.
        payload = undo if undo_data and out[offset:end] == new_data else new_data
        out[offset:end] = payload
    return bytes(out)


def apply_patch(source_path: str | Path, patch_path: str | Path, output_path: str | Path) -> dict[str, str]:
    source_path = Path(source_path)
    patch_path = Path(patch_path)
    output_path = Path(output_path)
    if source_path.resolve() == output_path.resolve():
        raise PatchError("The patched ROM must be saved as a new file. The source ROM is never overwritten.")
    if output_path.exists():
        raise FileExistsError(f"Output already exists: {output_path}")

    source = source_path.read_bytes()
    patch = patch_path.read_bytes()
    fmt = detect_patch_format(patch)
    if fmt == "IPS":
        result = _apply_ips(source, patch)
    elif fmt == "IPS32":
        result = _apply_ips(source, patch, ips32=True)
    elif fmt == "BPS":
        result = _apply_bps(source, patch)
    elif fmt == "UPS":
        result = _apply_ups(source, patch)
    elif fmt == "PPF":
        result = _apply_ppf(source, patch)
    else:
        raise PatchError(f"Unsupported patch format: {fmt}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(result)
    return {"format": fmt, **checksum_info(output_path)}
