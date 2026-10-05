"""Transcription engine interface.

A transcription engine turns an audio file into note events. Everything
downstream (chords, MIDI, MusicXML, piano roll) only depends on this
interface, so new models can be dropped in without touching the pipeline.

To add an engine:

1. Subclass :class:`TranscriptionEngine` in a new module in this package.
2. Implement :meth:`availability` (cheap check – no model loading) and
   :meth:`transcribe`.
3. Register it in ``registry.py``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from app.analysis.types import Note, Pedal
from app.config import Settings

# progress(fraction 0..1, optional status message)
ProgressFn = Callable[[float, str | None], None]


class TranscriptionUnavailable(Exception):
    """The engine can't run here (missing package, model, or configuration)."""


@dataclass
class EngineAvailability:
    available: bool
    reason: str | None = None
    install_hint: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class TranscriptionOutput:
    notes: list[Note]
    pedals: list[Pedal] = field(default_factory=list)
    model: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class TranscriptionEngine(ABC):
    id: ClassVar[str]
    label: ClassVar[str]
    description: ClassVar[str]
    # Whether the model is trained specifically on solo piano.
    piano_specific: ClassVar[bool] = False

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @classmethod
    @abstractmethod
    def availability(cls, settings: Settings) -> EngineAvailability:
        """Cheap check; must not import heavy ML packages or load models."""

    @abstractmethod
    def transcribe(self, audio_path: Path, progress: ProgressFn) -> TranscriptionOutput:
        """Transcribe a mono WAV file. Raise TranscriptionUnavailable if it can't run."""
