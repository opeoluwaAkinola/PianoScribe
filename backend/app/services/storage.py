"""Local filesystem storage.

Layout::

    data/storage/recordings/<recording_id>/
        original.<ext>        # the uploaded file, untouched
        audio.wav             # decoded mono PCM used for analysis
        playback.m4a          # browser-friendly audio for the player
        analyses/<analysis_id>/
            result.json
            transcription.mid
            score.musicxml
            score.pdf         # only when MuseScore is installed

Everything that touches paths goes through this module so the backend can be
swapped for object storage later without touching the pipeline.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, BinaryIO

from app.config import get_settings


class UploadTooLarge(Exception):
    pass


class LocalStorage:
    RESULT_FILE = "result.json"
    MIDI_FILE = "transcription.mid"
    MUSICXML_FILE = "score.musicxml"
    PDF_FILE = "score.pdf"

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or get_settings().storage_dir

    # --- Recordings ---------------------------------------------------------
    def recording_dir(self, recording_id: str) -> Path:
        return self.root / "recordings" / recording_id

    def original_path(self, recording_id: str, ext: str) -> Path:
        return self.recording_dir(recording_id) / f"original.{ext}"

    def audio_path(self, recording_id: str) -> Path:
        return self.recording_dir(recording_id) / "audio.wav"

    def playback_path(self, recording_id: str) -> Path:
        return self.recording_dir(recording_id) / "playback.m4a"

    def save_upload(self, recording_id: str, ext: str, stream: BinaryIO, max_bytes: int) -> tuple[Path, int]:
        dest = self.original_path(recording_id, ext)
        dest.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        # Write to a temp file first so a failed upload never leaves a partial
        # "original" behind.
        fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=".upload-")
        try:
            with os.fdopen(fd, "wb") as out:
                while chunk := stream.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise UploadTooLarge(f"File exceeds {max_bytes // (1024 * 1024)} MB")
                    out.write(chunk)
            os.replace(tmp, dest)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return dest, size

    def delete_recording(self, recording_id: str) -> None:
        shutil.rmtree(self.recording_dir(recording_id), ignore_errors=True)

    # --- Analyses -----------------------------------------------------------
    def analysis_dir(self, recording_id: str, analysis_id: str) -> Path:
        return self.recording_dir(recording_id) / "analyses" / analysis_id

    def analysis_file(self, recording_id: str, analysis_id: str, name: str) -> Path:
        return self.analysis_dir(recording_id, analysis_id) / name

    def write_json(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, separators=(",", ":"), allow_nan=False))
        os.replace(tmp, path)

    def read_json(self, path: Path) -> Any:
        return json.loads(path.read_text())

    def delete_analysis(self, recording_id: str, analysis_id: str) -> None:
        shutil.rmtree(self.analysis_dir(recording_id, analysis_id), ignore_errors=True)


def get_storage() -> LocalStorage:
    return LocalStorage()
