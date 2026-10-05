"""Stage definitions and DB-backed progress reporting for a running analysis."""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.db import session_scope
from app.models import Analysis, utcnow


@dataclass(frozen=True)
class StageDef:
    name: str
    label: str
    weight: float


STAGES: list[StageDef] = [
    StageDef("decode", "Decode audio", 4),
    StageDef("tempo", "Tempo, beats & meter", 8),
    StageDef("transcription", "AI piano transcription", 58),
    StageDef("key", "Key detection", 2),
    StageDef("chords", "Chord detection", 6),
    StageDef("sections", "Song sections", 6),
    StageDef("midi", "MIDI export", 2),
    StageDef("musicxml", "Sheet music (MusicXML)", 12),
    StageDef("pdf", "PDF (MuseScore)", 2),
]
STAGE_BY_NAME = {s.name: s for s in STAGES}
RENOTATE_SKIPS = {"decode", "transcription"}


class Cancelled(Exception):
    pass


def initial_stages(mode: str) -> list[dict]:
    return [
        {
            "name": s.name,
            "label": s.label,
            "status": "skipped" if mode == "renotate" and s.name in RENOTATE_SKIPS else "pending",
            "message": "Reusing previous result" if mode == "renotate" and s.name in RENOTATE_SKIPS else None,
            "started_at": None,
            "finished_at": None,
        }
        for s in STAGES
    ]


class ProgressReporter:
    """Writes stage/progress updates to the analysis row (throttled)."""

    def __init__(self, analysis_id: str, mode: str = "full", min_interval: float = 0.4) -> None:
        self.analysis_id = analysis_id
        self.mode = mode
        self.min_interval = min_interval
        self.stages = initial_stages(mode)
        self._active = [s for s in STAGES if not (mode == "renotate" and s.name in RENOTATE_SKIPS)]
        self._total = sum(s.weight for s in self._active)
        self._done_weight = 0.0
        self._current: StageDef | None = None
        self._last_write = 0.0
        self._message: str | None = None
        self._fraction = 0.0

    def _stage(self, name: str) -> dict:
        return next(s for s in self.stages if s["name"] == name)

    def _progress(self) -> float:
        cur = self._current.weight * self._fraction if self._current else 0.0
        return min(0.999, (self._done_weight + cur) / self._total) if self._total else 0.0

    def _write(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_write < self.min_interval:
            return
        self._last_write = now
        with session_scope() as db:
            a = db.get(Analysis, self.analysis_id)
            if a is None:
                raise Cancelled("Analysis was deleted")
            a.stages = [dict(s) for s in self.stages]
            a.stage = self._current.name if self._current else None
            a.stage_message = self._message
            a.progress = self._progress()
            if a.cancel_requested:
                raise Cancelled("Cancelled by user")

    def start(self, name: str, message: str | None = None) -> None:
        self._current = STAGE_BY_NAME[name]
        self._fraction = 0.0
        self._message = message
        st = self._stage(name)
        st.update(status="running", message=message, started_at=utcnow().isoformat())
        self._write(force=True)

    def update(self, fraction: float, message: str | None = None) -> None:
        self._fraction = max(0.0, min(1.0, fraction))
        if message is not None:
            self._message = message
            if self._current:
                self._stage(self._current.name)["message"] = message
        self._write()

    def finish(self, name: str, status: str = "done", message: str | None = None) -> None:
        st = self._stage(name)
        st.update(status=status, message=message, finished_at=utcnow().isoformat())
        self._done_weight += STAGE_BY_NAME[name].weight
        self._current = None
        self._fraction = 0.0
        self._message = None
        self._write(force=True)

    def skip(self, name: str, message: str, status: str = "skipped") -> None:
        st = self._stage(name)
        st.update(status=status, message=message, finished_at=utcnow().isoformat())
        self._done_weight += STAGE_BY_NAME[name].weight
        self._write(force=True)
