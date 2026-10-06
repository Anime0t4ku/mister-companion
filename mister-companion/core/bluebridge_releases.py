import urllib.request
import urllib.error
import json
import re
import time
import threading

BLUEBRIDGE_RELEASE_URL = "https://api.github.com/repos/Anime0t4ku/MC-BlueBridge/releases"

def version_key(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?", str(value).strip())
    if not match:
        raise ValueError("Invalid firmware version: " + str(value))
    pre = match.group(4)
    if pre:
        pre = re.sub(r"^beta-(\d+)$", r"beta.\1", pre)
    identifiers = tuple((0, int(p)) if p.isdigit() else (1, p) for p in (pre or "").split("."))
    return tuple(int(match.group(i)) for i in (1, 2, 3)) + (1 if pre is None else 0, identifiers)

def _lookup_bluebridge_release(installed="", opener=None):
    opener = opener or urllib.request.urlopen
    candidates = []
    stable_only = bool(installed and version_key(installed)[3])
    try:
        for page in range(1, 21):
            request = urllib.request.Request(BLUEBRIDGE_RELEASE_URL + "?per_page=100&page=" + str(page), headers={"User-Agent": "MiSTer-Companion-BlueBridge", "Accept": "application/vnd.github+json"})
            with opener(request, timeout=15) as response:
                releases = json.load(response)
            if not isinstance(releases, list):
                return {"available": False}
            for release in releases:
                if release.get("draft"):
                    continue
                try:
                    key = version_key(release.get("tag_name", ""))
                except ValueError:
                    continue
                if stable_only and (not key[3] or release.get("prerelease")):
                    continue
                for asset in release.get("assets", []):
                    url = asset.get("browser_download_url", "")
                    if asset.get("name") == "mc_bluebridge.uf2" and url.startswith("https://github.com/Anime0t4ku/MC-BlueBridge/releases/download/") and 0 < int(asset.get("size", 0)) <= 8 * 1024 * 1024:
                        candidates.append((key, release, asset))
                        break
            if len(releases) < 100:
                break
    except (OSError, ValueError, urllib.error.URLError):
        return {"available": False}
    if not candidates:
        return {"available": False}
    stable = [c for c in candidates if c[0][3] and not c[1].get("prerelease")]
    key, release, asset = max((stable or candidates) if not installed else candidates, key=lambda c: c[0])
    return {"available": True, "version": release["tag_name"].lstrip("v"), "url": asset["browser_download_url"], "size": asset["size"], "update_available": not installed or key > version_key(installed)}

def download_bluebridge_release(info):
    if not info.get("available") or not info.get("url", "").startswith("https://github.com/Anime0t4ku/MC-BlueBridge/releases/download/"):
        raise ValueError("No firmware release available")
    request = urllib.request.Request(info["url"], headers={"User-Agent": "MiSTer-Companion-BlueBridge"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(8 * 1024 * 1024 + 1)
    if not data or len(data) > 8 * 1024 * 1024 or len(data) != info["size"]:
        raise ValueError("Incomplete or oversized firmware download")
    return data

_release_cache = {}
_release_cache_lock = threading.RLock()

def bluebridge_release(installed="", opener=None):
    if opener is not None:
        return _lookup_bluebridge_release(installed, opener)
    with _release_cache_lock:
        entry = _release_cache.get(installed)
        if entry and time.monotonic() < entry[0]:
            return dict(entry[1])
        info = _lookup_bluebridge_release(installed)
        _release_cache[installed] = (time.monotonic() + (300 if info.get("available") else 60), info)
        return dict(info)
