"""Spotify Basic Pitch (Bittner et al., ICASSP 2022).

A lightweight, instrument-agnostic polyphonic note transcription model. Less
accurate on piano than the ByteDance model and it does not detect pedalling,
but it is small and fast.

Install: ``pip install basic-pitch`` (see https://github.com/spotify/basic-pitch
for the Python versions it currently supports).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from app.analysis.types import Note
from app.config import Settings
from app.transcription.base import (
    EngineAvailability,
    ProgressFn,
    TranscriptionEngine,
    TranscriptionOutput,
    TranscriptionUnavailable,
)


class BasicPitchEngine(TranscriptionEngine):
    id = "basic_pitch"
    label = "Spotify Basic Pitch"
    description = (
        "Lightweight polyphonic transcription (Bittner et al. 2022). Works on any instrument; "
        "less accurate than piano-specific models and no pedal detection."
    )
    piano_specific = False

    @classmethod
    def availability(cls, settings: Settings) -> EngineAvailability:
        if importlib.util.find_spec("basic_pitch") is None:
            return EngineAvailability(
                False,
                reason="Python package not installed: basic-pitch",
                install_hint="cd backend && .venv/bin/python -m pip install basic-pitch",
            )
        return EngineAvailability(True)

    def transcribe(self, audio_path: Path, progress: ProgressFn) -> TranscriptionOutput:
        if importlib.util.find_spec("basic_pitch") is None:
            raise TranscriptionUnavailable("basic-pitch is not installed")
        from basic_pitch import ICASSP_2022_MODEL_PATH
        from basic_pitch.inference import predict

        progress(0.1, "Running Basic Pitch")
        _, _, note_events = predict(
            str(audio_path),
            ICASSP_2022_MODEL_PATH,
            onset_threshold=0.5,
            frame_threshold=0.3,
            minimum_note_length=58,  # ms
            minimum_frequency=27.5,  # A0
            maximum_frequency=4186.0,  # C8
            multiple_pitch_bends=False,
            melodia_trick=True,
        )
        notes = [
            Note(int(pitch), float(start), float(end), int(max(1, min(127, round(amp * 127)))))
            for start, end, pitch, amp, *_ in note_events
        ]
        progress(1.0, None)
        return TranscriptionOutput(notes=notes, model="ICASSP 2022")
