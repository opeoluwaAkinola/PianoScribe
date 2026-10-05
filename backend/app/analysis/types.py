"""Core value types shared by transcription engines, analysis and notation."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class Note:
    pitch: int  # MIDI note number (21 = A0 … 108 = C8)
    start: float  # seconds
    end: float  # seconds
    velocity: int  # 1-127

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict:
        return {
            "pitch": self.pitch,
            "start": round(self.start, 4),
            "end": round(self.end, 4),
            "velocity": self.velocity,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Note:
        return cls(int(d["pitch"]), float(d["start"]), float(d["end"]), int(d["velocity"]))


@dataclass
class Pedal:
    """Sustain pedal (CC64) down interval."""

    start: float
    end: float

    def to_dict(self) -> dict:
        return {"start": round(self.start, 4), "end": round(self.end, 4)}

    @classmethod
    def from_dict(cls, d: dict) -> Pedal:
        return cls(float(d["start"]), float(d["end"]))


def clean_notes(notes: list[Note], min_duration: float = 0.01) -> list[Note]:
    """Clamp values to valid MIDI ranges and drop degenerate notes."""
    out = []
    for n in notes:
        if n.end - n.start < min_duration or not 0 <= n.pitch <= 127:
            continue
        out.append(Note(int(n.pitch), max(0.0, float(n.start)), float(n.end), int(min(127, max(1, n.velocity)))))
    out.sort(key=lambda n: (n.start, n.pitch))
    return out


def sustained_notes(notes: list[Note], pedals: list[Pedal]) -> list[Note]:
    """Extend note releases while the sustain pedal is held.

    This reflects what is *heard* (useful for harmony analysis), not which keys
    are physically held (which is what notation needs).
    """
    if not pedals:
        return notes
    by_pitch: dict[int, list[Note]] = {}
    for n in notes:
        by_pitch.setdefault(n.pitch, []).append(n)
    out: list[Note] = []
    for same in by_pitch.values():
        same.sort(key=lambda n: n.start)
        for i, n in enumerate(same):
            end = n.end
            for p in pedals:
                if p.start <= n.end < p.end:
                    end = max(end, p.end)
                    break
            if i + 1 < len(same):
                # A re-struck key cuts off the previous sound.
                end = min(end, same[i + 1].start)
            if end > n.start:
                out.append(Note(n.pitch, n.start, end, n.velocity))
    out.sort(key=lambda n: (n.start, n.pitch))
    return out


__all__ = ["Note", "Pedal", "asdict", "clean_notes", "sustained_notes"]
