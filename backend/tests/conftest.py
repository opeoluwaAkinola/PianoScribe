"""Test fixtures: every test session gets an isolated data directory."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

# Must happen before the app is imported anywhere.
_DATA_DIR = Path(tempfile.mkdtemp(prefix="pianoscribe-test-"))
os.environ["PIANOSCRIBE_DATA_DIR"] = str(_DATA_DIR)
_real_models = Path(__file__).resolve().parent.parent / "data" / "models"
if _real_models.exists():
    # Reuse downloaded checkpoints instead of fetching them again.
    (_DATA_DIR / "models").symlink_to(_real_models, target_is_directory=True)

import pytest  # noqa: E402

from app.devtools.synth import gospel_progression, write_wav  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def isolated_data_dir():
    from app import db
    from app.config import get_settings

    get_settings.cache_clear()
    db.reset_engine()
    db.init_db()
    yield _DATA_DIR
    db.reset_engine()
    shutil.rmtree(_DATA_DIR, ignore_errors=True)


@pytest.fixture(scope="session")
def reference_notes():
    return gospel_progression(bpm=76.0, bars=8)


@pytest.fixture(scope="session")
def test_wav(tmp_path_factory, reference_notes) -> Path:
    return write_wav(tmp_path_factory.mktemp("audio") / "gospel.wav", reference_notes)


@pytest.fixture(scope="session")
def media_files(tmp_path_factory, test_wav) -> dict[str, Path]:
    """The synthetic recording encoded in every supported upload format."""
    from app.services.media import require_ffmpeg

    ff = require_ffmpeg()
    out_dir = tmp_path_factory.mktemp("formats")
    files = {"wav": test_wav}
    audio_args = {"mp3": ["-c:a", "libmp3lame", "-b:a", "128k"], "m4a": ["-c:a", "aac"], "flac": ["-c:a", "flac"]}
    for ext, args in audio_args.items():
        dst = out_dir / f"gospel.{ext}"
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(test_wav), *args, str(dst)], check=True)
        files[ext] = dst
    for ext in ("mp4", "mov"):
        dst = out_dir / f"gospel.{ext}"
        subprocess.run(
            [
                ff,
                "-y",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=160x120:r=10",
                "-i",
                str(test_wav),
                "-shortest",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(dst),
            ],
            check=True,
        )
        files[ext] = dst
    return files
