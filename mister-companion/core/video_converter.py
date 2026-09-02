from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import threading
import zipfile
from pathlib import Path

import requests

from core.app_paths import app_base_dir, generated_path


FFMPEG_VERSION = "9.0"
FFMPEG_DIR = generated_path("tools", "ffmpeg", default_root=app_base_dir())

_BTBN_RELEASE_BASE = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest"
_MARTIN_RIEDL_BASE = "https://ffmpeg.martin-riedl.de/redirect/latest/macos"

_PACKAGES = {
    "windows-x64": {
        "archives": [f"{_BTBN_RELEASE_BASE}/ffmpeg-n9.0-latest-win64-gpl-9.0.zip"],
        "filenames": ["ffmpeg-windows-x64.zip"],
    },
    "windows-arm64": {
        "archives": [f"{_BTBN_RELEASE_BASE}/ffmpeg-n9.0-latest-winarm64-gpl-9.0.zip"],
        "filenames": ["ffmpeg-windows-arm64.zip"],
    },
    "linux-x64": {
        "archives": [f"{_BTBN_RELEASE_BASE}/ffmpeg-n9.0-latest-linux64-gpl-9.0.tar.xz"],
        "filenames": ["ffmpeg-linux-x64.tar.xz"],
    },
    "linux-arm64": {
        "archives": [f"{_BTBN_RELEASE_BASE}/ffmpeg-n9.0-latest-linuxarm64-gpl-9.0.tar.xz"],
        "filenames": ["ffmpeg-linux-arm64.tar.xz"],
    },
    "macos-x64": {
        "archives": [
            f"{_MARTIN_RIEDL_BASE}/amd64/release/ffmpeg.zip",
            f"{_MARTIN_RIEDL_BASE}/amd64/release/ffprobe.zip",
        ],
        "filenames": ["ffmpeg-macos-x64.zip", "ffprobe-macos-x64.zip"],
    },
    "macos-arm64": {
        "archives": [
            f"{_MARTIN_RIEDL_BASE}/arm64/release/ffmpeg.zip",
            f"{_MARTIN_RIEDL_BASE}/arm64/release/ffprobe.zip",
        ],
        "filenames": ["ffmpeg-macos-arm64.zip", "ffprobe-macos-arm64.zip"],
    },
}

_TEXT_SUBTITLE_CODECS = {
    "ass", "ssa", "subrip", "srt", "webvtt", "mov_text", "text", "microdvd",
    "mpl2", "jacosub", "sami", "realtext", "subviewer", "subviewer1", "vplayer",
}


class VideoConverterError(RuntimeError):
    pass


def _windows_no_console_kwargs() -> dict[str, int]:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def platform_key() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    arm64 = machine in {"arm64", "aarch64"}
    if system == "windows":
        return "windows-arm64" if arm64 else "windows-x64"
    if system == "darwin":
        return "macos-arm64" if arm64 else "macos-x64"
    if system == "linux":
        return "linux-arm64" if arm64 else "linux-x64"
    raise VideoConverterError(f"Unsupported platform: {platform.system()} {platform.machine()}")


def ffmpeg_executable() -> Path:
    return FFMPEG_DIR / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")


def ffprobe_executable() -> Path:
    return FFMPEG_DIR / ("ffprobe.exe" if os.name == "nt" else "ffprobe")


def has_ffmpeg() -> bool:
    return ffmpeg_executable().is_file() and ffprobe_executable().is_file()


def remove_ffmpeg() -> None:
    if FFMPEG_DIR.exists():
        shutil.rmtree(FFMPEG_DIR)


def _download(url: str, target: Path, progress_callback=None, base=0, span=100) -> None:
    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0) or 0)
        done = 0
        with target.open("wb") as handle:
            for chunk in response.iter_content(1024 * 512):
                if not chunk:
                    continue
                handle.write(chunk)
                done += len(chunk)
                if progress_callback and total:
                    progress_callback(base + int((done / total) * span), 100)


def _extract_archive(archive: Path, destination: Path) -> None:
    if archive.name.lower().endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(destination)
        return
    if archive.name.lower().endswith((".tar.xz", ".txz", ".tar.gz", ".tgz", ".tar")):
        with tarfile.open(archive, "r:*") as tf:
            try:
                tf.extractall(destination, filter="data")
            except TypeError:
                tf.extractall(destination)
        return
    raise VideoConverterError(f"Unsupported FFmpeg package: {archive.name}")


def _find_binary(root: Path, name: str) -> Path | None:
    wanted = name.lower() + (".exe" if os.name == "nt" else "")
    for path in root.rglob("*"):
        if path.is_file() and path.name.lower() == wanted:
            return path
    return None


def _verify_binary(path: Path, expected_name: str) -> None:
    try:
        result = subprocess.run(
            [str(path), "-version"], capture_output=True, text=True, errors="replace",
            timeout=20, **_windows_no_console_kwargs(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise VideoConverterError(f"Could not start {expected_name} after download: {exc}") from exc
    output = ((result.stdout or "") + "\n" + (result.stderr or "")).lower()
    if result.returncode != 0 or expected_name not in output:
        raise VideoConverterError(f"The downloaded {expected_name} executable could not be verified.")


def download_ffmpeg(progress_callback=None) -> Path:
    package = _PACKAGES.get(platform_key())
    if not package:
        raise VideoConverterError(f"No FFmpeg package is configured for {platform_key()}.")

    FFMPEG_DIR.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mister-companion-ffmpeg-") as tmp:
        tmpdir = Path(tmp)
        unpacked = tmpdir / "unpacked"
        unpacked.mkdir()
        urls = package["archives"]
        filenames = package["filenames"]
        for index, (url, filename) in enumerate(zip(urls, filenames)):
            span = max(1, 100 // len(urls))
            archive = tmpdir / filename
            _download(url, archive, progress_callback, index * span, span)
            _extract_archive(archive, unpacked)

        ffmpeg = _find_binary(unpacked, "ffmpeg")
        ffprobe = _find_binary(unpacked, "ffprobe")
        if not ffmpeg or not ffprobe:
            raise VideoConverterError("The FFmpeg download did not contain both FFmpeg and FFprobe.")

        staged = tmpdir / "staged"
        staged.mkdir()
        shutil.copy2(ffmpeg, staged / ffmpeg_executable().name)
        shutil.copy2(ffprobe, staged / ffprobe_executable().name)
        for candidate in unpacked.rglob("*"):
            if candidate.is_file() and candidate.name.lower().startswith(("license", "copying")):
                target = staged / candidate.name
                if not target.exists():
                    shutil.copy2(candidate, target)

        if FFMPEG_DIR.exists():
            shutil.rmtree(FFMPEG_DIR)
        shutil.copytree(staged, FFMPEG_DIR)

    if os.name != "nt":
        for binary in (ffmpeg_executable(), ffprobe_executable()):
            binary.chmod(binary.stat().st_mode | 0o755)
    _verify_binary(ffmpeg_executable(), "ffmpeg")
    _verify_binary(ffprobe_executable(), "ffprobe")
    if progress_callback:
        progress_callback(100, 100)
    return ffmpeg_executable()


def _ratio(value: str | None, fallback=1.0) -> float:
    try:
        left, right = str(value or "").split(":", 1)
        right_value = float(right)
        return float(left) / right_value if right_value else fallback
    except (ValueError, TypeError):
        return fallback


def _channel_label(stream: dict) -> str:
    layout = str(stream.get("channel_layout") or "").strip()
    channels = int(stream.get("channels") or 0)
    if layout:
        return layout.replace("mono", "Mono").replace("stereo", "Stereo")
    if channels == 1:
        return "Mono"
    if channels == 2:
        return "Stereo"
    if channels:
        return f"{channels} channels"
    return "Unknown channels"


def _stream_label(kind: str, ordinal: int, stream: dict) -> str:
    tags = stream.get("tags") or {}
    language = str(tags.get("language") or "Unknown language")
    title = str(tags.get("title") or "").strip()
    codec = str(stream.get("codec_name") or "unknown").upper()
    parts = [f"{kind} {ordinal + 1}", language]
    if title and title.lower() != language.lower():
        parts.append(title)
    parts.append(codec)
    if kind == "Audio":
        parts.append(_channel_label(stream))
    return " – ".join(parts)


def probe_video(path: str | Path) -> dict:
    if not has_ffmpeg():
        raise VideoConverterError("Download FFmpeg first.")
    command = [
        str(ffprobe_executable()), "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    result = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120, **_windows_no_console_kwargs(),
    )
    if result.returncode != 0:
        raise VideoConverterError((result.stderr or "FFprobe could not inspect the selected video.").strip())
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise VideoConverterError("FFprobe returned invalid stream information.") from exc

    streams = data.get("streams") or []
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    if not video_streams:
        raise VideoConverterError("The selected file does not contain a video stream.")
    video = video_streams[0]
    duration = float((data.get("format") or {}).get("duration") or video.get("duration") or 0)
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    dar = _ratio(video.get("display_aspect_ratio"), 0.0)
    if not dar and width and height:
        dar = (width / height) * _ratio(video.get("sample_aspect_ratio"), 1.0)
    transfer = str(video.get("color_transfer") or "").lower()
    primaries = str(video.get("color_primaries") or "").lower()
    colorspace = str(video.get("color_space") or "").lower()
    hdr = transfer in {"smpte2084", "arib-std-b67"} or primaries.startswith("bt2020") or colorspace.startswith("bt2020")

    audio = []
    subtitles = []
    for stream in streams:
        if stream.get("codec_type") == "audio":
            ordinal = len(audio)
            audio.append({
                "ordinal": ordinal,
                "index": int(stream.get("index") or 0),
                "codec": str(stream.get("codec_name") or "unknown"),
                "channels": int(stream.get("channels") or 0),
                "channel_layout": str(stream.get("channel_layout") or ""),
                "label": _stream_label("Audio", ordinal, stream),
            })
        elif stream.get("codec_type") == "subtitle":
            ordinal = len(subtitles)
            codec = str(stream.get("codec_name") or "unknown")
            subtitles.append({
                "ordinal": ordinal,
                "index": int(stream.get("index") or 0),
                "codec": codec,
                "text": codec.lower() in _TEXT_SUBTITLE_CODECS,
                "label": _stream_label("Subtitle", ordinal, stream),
            })
    if not audio:
        raise VideoConverterError("The selected file does not contain an audio stream.")
    return {
        "duration": duration,
        "width": width,
        "height": height,
        "display_aspect_ratio": dar or (4 / 3),
        "hdr": hdr,
        "transfer": transfer,
        "audio": audio,
        "subtitles": subtitles,
    }


def output_channel_choices(audio_stream: dict) -> list[tuple[str, int | None]]:
    channels = int(audio_stream.get("channels") or 0)
    layout = str(audio_stream.get("channel_layout") or "").lower()
    if channels <= 1 or layout == "mono":
        return [("Mono (original)", None), ("Stereo", 2)]
    if channels == 2 or layout == "stereo":
        return [("Stereo (original)", None)]
    if channels <= 6:
        return [("5.1 (original)" if channels == 6 else f"{channels} channels (original)", None), ("Stereo downmix", 2)]
    return [("5.1 downmix", 6), ("Stereo downmix", 2)]


def _escape_subtitles_filename(path: Path) -> str:
    text = str(path.resolve()).replace("\\", "/")
    text = text.replace("'", r"\'").replace(":", r"\:")
    return text


def _even(value: float, minimum=2) -> int:
    rounded = max(minimum, int(round(value)))
    return rounded if rounded % 2 == 0 else rounded - 1


def _dvd_geometry(source_dar: float, standard: str) -> tuple[int, int, int, int, str]:
    standard = standard.lower()
    target_w, target_h = (720, 576) if standard == "pal" else (720, 480)
    dvd_aspect = "4:3" if source_dar < 1.55 else "16:9"
    target_sar = (16 / 15 if standard == "pal" else 8 / 9) if dvd_aspect == "4:3" else (64 / 45 if standard == "pal" else 32 / 27)
    pixel_ratio = max(0.01, source_dar / target_sar)
    if pixel_ratio >= target_w / target_h:
        content_w = target_w
        content_h = _even(target_w / pixel_ratio)
    else:
        content_h = target_h
        content_w = _even(target_h * pixel_ratio)
    return target_w, target_h, min(content_w, target_w), min(content_h, target_h), dvd_aspect


def convert_video(
    input_path: str | Path,
    output_path: str | Path,
    probe: dict,
    standard: str,
    audio_ordinal: int,
    subtitle_ordinal: int | None,
    output_channels: int | None,
    progress_callback=None,
    log_callback=None,
) -> Path:
    if not has_ffmpeg():
        raise VideoConverterError("Download FFmpeg first.")
    input_path = Path(input_path)
    output_path = Path(output_path)
    if output_path.exists():
        raise FileExistsError(f"Output already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if audio_ordinal < 0 or audio_ordinal >= len(probe["audio"]):
        raise VideoConverterError("The selected audio stream is no longer available.")

    target_w, target_h, content_w, content_h, dvd_aspect = _dvd_geometry(
        float(probe.get("display_aspect_ratio") or 4 / 3), standard
    )
    filters = []
    if probe.get("hdr"):
        filters.extend([
            "zscale=t=linear:npl=100",
            "format=gbrpf32le",
            "tonemap=hable:desat=0",
            "zscale=p=bt709:t=bt709:m=bt709:r=tv",
            "format=yuv420p",
        ])

    subtitle = None
    if subtitle_ordinal is not None:
        if subtitle_ordinal < 0 or subtitle_ordinal >= len(probe["subtitles"]):
            raise VideoConverterError("The selected subtitle stream is no longer available.")
        subtitle = probe["subtitles"][subtitle_ordinal]
        if subtitle.get("text"):
            escaped = _escape_subtitles_filename(input_path)
            filters.append(f"subtitles=filename='{escaped}':si={subtitle_ordinal}")

    filters.extend([
        f"scale={content_w}:{content_h}:flags=lanczos",
        f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black",
        "format=yuv420p",
    ])
    chain = ",".join(filters)
    if subtitle and not subtitle.get("text"):
        filter_complex = f"[0:v:0]{','.join(filters[:-3]) + ',' if filters[:-3] else ''}format=yuv420p[base];[base][0:s:{subtitle_ordinal}]overlay,{','.join(filters[-3:])}[vout]"
    else:
        filter_complex = f"[0:v:0]{chain}[vout]"

    command = [
        str(ffmpeg_executable()), "-hide_banner", "-y", "-i", str(input_path),
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", f"0:a:{audio_ordinal}",
        "-target", f"{standard.lower()}-dvd", "-aspect", dvd_aspect,
        "-c:a", "ac3", "-ar", "48000", "-b:a", "448k",
    ]
    if output_channels:
        command.extend(["-ac", str(output_channels)])
    command.extend([
        "-color_range", "tv", "-progress", "pipe:1", "-nostats", str(output_path),
    ])

    if log_callback:
        log_callback("Command: " + subprocess.list2cmdline(command))
    proc = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace", bufsize=1, **_windows_no_console_kwargs(),
    )
    assert proc.stdout is not None and proc.stderr is not None
    def read_stderr():
        for line in proc.stderr:
            if log_callback:
                log_callback(line.rstrip())

    thread = threading.Thread(target=read_stderr, daemon=True)
    thread.start()
    duration = float(probe.get("duration") or 0)
    speed = ""
    for raw in proc.stdout:
        line = raw.strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key == "speed":
            speed = value
        elif key in {"out_time_us", "out_time_ms"} and duration > 0:
            try:
                converted = int(value) / 1_000_000
                percent = max(0, min(99, int(converted * 100 / duration)))
                if progress_callback:
                    progress_callback(percent, speed)
            except ValueError:
                pass
        elif key == "progress" and value == "end" and progress_callback:
            progress_callback(100, speed)
    code = proc.wait()
    thread.join(timeout=2)
    if code != 0:
        output_path.unlink(missing_ok=True)
        raise VideoConverterError(f"FFmpeg exited with code {code}.")
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise VideoConverterError("FFmpeg completed without creating a valid MPEG output file.")
    return output_path
