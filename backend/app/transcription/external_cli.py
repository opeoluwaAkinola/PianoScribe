"""Run any command-line transcriber that writes a MIDI file.

This is the quickest way to try a new model without writing Python glue.
Set ``PIANOSCRIBE_EXTERNAL_CLI_COMMAND`` to a template containing
``{input}`` (a 44.1 kHz mono WAV) and ``{output}`` (the MIDI path to write)::

    # Transkun (Yan & Duan) – pip install transkun
    PIANOSCRIBE_EXTERNAL_CLI_COMMAND="transkun {input} {output}"

    # Any script of your own
    PIANOSCRIBE_EXTERNAL_CLI_COMMAND="python /path/to/my_model.py --in {input} --out {output}"
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.config import Settings
from app.notation.midi import read_midi_notes
from app.transcription.base import (
    EngineAvailability,
    ProgressFn,
    TranscriptionEngine,
    TranscriptionOutput,
    TranscriptionUnavailable,
)


class ExternalCliEngine(TranscriptionEngine):
    id = "external_cli"
    label = "External command"
    description = (
        "Runs a command-line transcription model of your choice that writes a MIDI file "
        "(configured with PIANOSCRIBE_EXTERNAL_CLI_COMMAND)."
    )

    @classmethod
    def availability(cls, settings: Settings) -> EngineAvailability:
        cmd = settings.external_cli_command
        if not cmd:
            return EngineAvailability(
                False,
                reason="No command configured.",
                install_hint='Set PIANOSCRIBE_EXTERNAL_CLI_COMMAND="transkun {input} {output}" in backend/.env',
            )
        if "{input}" not in cmd or "{output}" not in cmd:
            return EngineAvailability(False, reason="Command must contain {input} and {output} placeholders.")
        exe = shlex.split(cmd)[0]
        if shutil.which(exe) is None and not Path(exe).exists():
            return EngineAvailability(False, reason=f"Executable not found: {exe}")
        return EngineAvailability(True, details={"command": cmd})

    def transcribe(self, audio_path: Path, progress: ProgressFn) -> TranscriptionOutput:
        avail = self.availability(self.settings)
        if not avail.available:
            raise TranscriptionUnavailable(avail.reason or "External command unavailable")
        template = self.settings.external_cli_command or ""
        with tempfile.TemporaryDirectory(prefix="pianoscribe-") as tmp:
            out = Path(tmp) / "out.mid"
            args = [
                part.replace("{input}", str(audio_path)).replace("{output}", str(out)) for part in shlex.split(template)
            ]
            progress(0.05, f"Running {args[0]}")
            proc = subprocess.run(args, capture_output=True, text=True, timeout=self.settings.external_cli_timeout_sec)
            if proc.returncode != 0 or not out.exists():
                tail = "\n".join((proc.stderr or proc.stdout).strip().splitlines()[-5:])
                raise RuntimeError(f"External transcriber failed (exit {proc.returncode}): {tail}")
            notes, pedals = read_midi_notes(out)
        progress(1.0, None)
        return TranscriptionOutput(notes=notes, pedals=pedals, model=args[0])
