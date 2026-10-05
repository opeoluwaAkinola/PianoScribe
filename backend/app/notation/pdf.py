"""Optional PDF rendering through MuseScore's command-line interface.

If MuseScore isn't installed the app still offers printable sheet music: the
web UI renders the MusicXML and you can print / save as PDF from the browser.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from app.config import get_settings

_CANDIDATES = [
    "/Applications/MuseScore 4.app/Contents/MacOS/mscore",
    "/Applications/MuseScore 3.app/Contents/MacOS/mscore",
    "C:/Program Files/MuseScore 4/bin/MuseScore4.exe",
    "C:/Program Files/MuseScore 3/bin/MuseScore3.exe",
]


@lru_cache
def find_musescore() -> str | None:
    configured = get_settings().musescore_path
    if configured and Path(configured).exists():
        return configured
    for name in ("mscore", "musescore", "mscore4portable", "MuseScore4", "musescore4", "mscore3"):
        if found := shutil.which(name):
            return found
    for c in _CANDIDATES:
        if Path(c).exists():
            return c
    return None


def render_pdf(musicxml: Path, pdf: Path, timeout: int = 180) -> None:
    exe = find_musescore()
    if not exe:
        raise RuntimeError("MuseScore not found")
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    tmp = pdf.with_suffix(".tmp.pdf")
    proc = subprocess.run(
        [exe, "-o", str(tmp), str(musicxml)], capture_output=True, text=True, timeout=timeout, env=env
    )
    if proc.returncode != 0 or not tmp.exists():
        tail = "\n".join((proc.stderr or proc.stdout).strip().splitlines()[-3:])
        raise RuntimeError(f"MuseScore failed: {tail}")
    tmp.replace(pdf)
