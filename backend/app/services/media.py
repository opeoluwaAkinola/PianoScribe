"""Audio/video decoding via ffmpeg.

ffmpeg is looked up in this order: ``PIANOSCRIBE_FFMPEG_PATH``, ``PATH``, and
finally the static binary bundled with the ``imageio-ffmpeg`` package, so a
fresh checkout works without installing ffmpeg system-wide.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import get_settings


class MediaError(Exception):
    pass


@dataclass
class MediaInfo:
    duration_sec: float | None
    sample_rate: int | None
    channels: int | None
    audio_codec: str | None
    has_audio: bool
    has_video: bool


@lru_cache
def find_ffmpeg() -> str | None:
    settings = get_settings()
    if settings.ffmpeg_path and Path(settings.ffmpeg_path).exists():
        return settings.ffmpeg_path
    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # pragma: no cover - depends on environment
        return None


def require_ffmpeg() -> str:
    exe = find_ffmpeg()
    if not exe:
        raise MediaError("ffmpeg not found. Install it (brew install ffmpeg) or `pip install imageio-ffmpeg`.")
    return exe


def ffmpeg_version() -> str | None:
    exe = find_ffmpeg()
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=10)
        first = out.stdout.splitlines()[0] if out.stdout else ""
        m = re.search(r"ffmpeg version (\S+)", first)
        return m.group(1) if m else first or None
    except Exception:
        return None


_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_AUDIO_RE = re.compile(r"Stream #\S+.*?Audio:\s*([^,\s]+)[^,]*,\s*(\d+)\s*Hz,\s*([^,]+)")
_VIDEO_RE = re.compile(r"Stream #\S+.*?Video:\s*(?!mjpeg|png)")  # cover art isn't video

_CHANNEL_LAYOUTS = {"mono": 1, "stereo": 2, "2.1": 3, "quad": 4, "5.0": 5, "5.1": 6, "7.1": 8}


def probe(path: Path) -> MediaInfo:
    """Inspect a media file by parsing ``ffmpeg -i`` output."""
    exe = require_ffmpeg()
    proc = subprocess.run(
        [exe, "-hide_banner", "-nostdin", "-i", str(path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    text = proc.stderr
    if "Invalid data found" in text or "No such file" in text:
        raise MediaError("The file could not be read as audio or video.")

    duration = None
    if m := _DURATION_RE.search(text):
        h, mnt, s = m.groups()
        duration = int(h) * 3600 + int(mnt) * 60 + float(s)

    codec = sr = channels = None
    has_audio = False
    if m := _AUDIO_RE.search(text):
        has_audio = True
        codec, sr_s, layout = m.groups()
        sr = int(sr_s)
        layout = layout.strip().split("(")[0].strip()
        channels = _CHANNEL_LAYOUTS.get(layout)
        if channels is None and (cm := re.match(r"(\d+)\s*channels", layout)):
            channels = int(cm.group(1))

    return MediaInfo(
        duration_sec=duration,
        sample_rate=sr,
        channels=channels,
        audio_codec=codec,
        has_audio=has_audio,
        has_video=bool(_VIDEO_RE.search(text)),
    )


def _run(cmd: list[str], timeout: int = 1800) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-5:])
        raise MediaError(f"ffmpeg failed: {tail}")


def decode_to_wav(src: Path, dst: Path, sample_rate: int = 44100) -> None:
    """Decode any supported input to mono 16-bit PCM WAV."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".tmp.wav")
    _run(
        [
            require_ffmpeg(),
            "-hide_banner",
            "-nostdin",
            "-y",
            "-i",
            str(src),
            "-vn",
            "-sn",
            "-dn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_s16le",
            str(tmp),
        ]
    )
    tmp.replace(dst)


def make_playback_audio(src: Path, dst: Path) -> None:
    """Transcode to AAC/M4A, which every modern browser can play and seek."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".tmp.m4a")
    _run(
        [
            require_ffmpeg(),
            "-hide_banner",
            "-nostdin",
            "-y",
            "-i",
            str(src),
            "-vn",
            "-sn",
            "-dn",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(tmp),
        ]
    )
    tmp.replace(dst)
