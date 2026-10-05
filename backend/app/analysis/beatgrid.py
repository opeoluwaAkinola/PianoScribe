"""The "score clock": a mapping between seconds and musical beat positions.

Live performances drift in tempo, so a constant-BPM grid would make bar lines
wander away from the music. Instead, detected beats are used as anchors and
time is interpolated between them. MIDI export, MusicXML engraving, chord bar
numbers and the piano-roll grid all use this one mapping so they agree.

Beat position 0 is the start of bar 1. Detected beats are placed so that the
detected downbeats land exactly on bar lines; anything before the first
detected beat is extrapolated at the opening tempo (a pickup). Bar 1 is the
bar containing the first musical event, so leading silence doesn't produce
empty bars (positions before it may be negative).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class BeatGrid:
    beat_times: np.ndarray  # detected beat times in seconds (len >= 2)
    beats_per_bar: int  # 4 for 4/4 and 12/8, 3 for 3/4
    compound: bool  # True for 12/8 (each beat = dotted quarter, divided in 3)
    lead_in: int  # score beat position of beat_times[0]
    duration: float
    _t: np.ndarray = field(init=False, repr=False)
    _b: np.ndarray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        bt = np.asarray(self.beat_times, dtype=float)
        if len(bt) < 2:
            raise ValueError("BeatGrid needs at least two beats")
        self.beat_times = bt
        ibi_first = float(np.median(np.diff(bt[: min(len(bt), 5)])))
        ibi_last = float(np.median(np.diff(bt[-min(len(bt), 5) :])))
        pos = self.lead_in + np.arange(len(bt), dtype=float)
        t = list(bt)
        b = list(pos)
        # Extrapolate backward to time 0 at the opening tempo.
        if bt[0] > 0:
            t.insert(0, 0.0)
            b.insert(0, pos[0] - bt[0] / ibi_first)
        # Extrapolate forward past the end at the closing tempo.
        end = max(self.duration, bt[-1]) + 4 * ibi_last
        t.append(end)
        b.append(pos[-1] + (end - bt[-1]) / ibi_last)
        self._t = np.asarray(t)
        self._b = np.asarray(b)

    # --- Construction -------------------------------------------------------
    @classmethod
    def from_detection(
        cls,
        beat_times: np.ndarray,
        beats_per_bar: int,
        first_downbeat_index: int,
        compound: bool,
        duration: float,
        origin_time: float = 0.0,
    ) -> BeatGrid:
        """``origin_time`` is the first musical event; it must fall in bar 1."""
        bt = np.asarray(beat_times, dtype=float)
        phase = (beats_per_bar - first_downbeat_index % beats_per_bar) % beats_per_bar
        probe = cls(bt, beats_per_bar, compound, 0, duration)
        rel = float(probe.time_to_beat(max(0.0, origin_time)))  # position with lead_in = 0
        # Smallest lead_in ≡ phase (mod bar) that keeps the origin at position
        # >= 0, tolerating notes played up to a quarter beat ahead of bar 1.
        k = int(np.ceil((-rel - phase - 0.25) / beats_per_bar - 1e-9))
        lead_in = phase + k * beats_per_bar
        return cls(bt, beats_per_bar, compound, lead_in, duration)

    @classmethod
    def constant(cls, bpm: float, duration: float, beats_per_bar: int = 4, compound: bool = False) -> BeatGrid:
        """Fallback grid when beat tracking found nothing usable."""
        ibi = 60.0 / bpm
        n = max(2, int(np.ceil(duration / ibi)) + 1)
        return cls(np.arange(n) * ibi, beats_per_bar, compound, 0, duration)

    # --- Mapping ------------------------------------------------------------
    def time_to_beat(self, t):
        return np.interp(t, self._t, self._b)

    def beat_to_time(self, b):
        return np.interp(b, self._b, self._t)

    @property
    def start_position(self) -> float:
        """Beat position of time 0 (negative when the recording opens with silence)."""
        return float(self._b[0])

    @property
    def beat_ql(self) -> float:
        """Quarter-note length of one beat (1.5 for compound meters)."""
        return 1.5 if self.compound else 1.0

    @property
    def time_signature(self) -> str:
        if self.compound:
            return f"{self.beats_per_bar * 3}/8"
        return f"{self.beats_per_bar}/4"

    @property
    def subdivisions(self) -> int:
        """Default quantisation steps per beat (16ths for simple, 8ths for compound)."""
        return 3 if self.compound else 4

    def bar_count(self) -> int:
        last = float(self.time_to_beat(self.duration))
        return max(1, int(np.ceil(last / self.beats_per_bar - 1e-6)))

    def bar_index(self, t: float) -> int:
        """0-based bar index of time ``t`` (clamped to bar 1)."""
        return max(0, int(np.floor(float(self.time_to_beat(t)) / self.beats_per_bar + 1e-9)))

    def downbeat_times(self) -> list[float]:
        bars = self.bar_count()
        times = self.beat_to_time(np.arange(bars + 1) * self.beats_per_bar)
        return [float(x) for x in times if 0 <= x <= self.duration]

    def all_beat_times(self) -> list[float]:
        last = float(self.time_to_beat(self.duration))
        first = int(np.ceil(self.start_position))
        pos = np.arange(first, int(np.floor(last)) + 1)
        return [float(x) for x in self.beat_to_time(pos)]

    def anchors(self) -> tuple[np.ndarray, np.ndarray]:
        """(times, beat positions) breakpoints of the piecewise-linear map."""
        return self._t.copy(), self._b.copy()

    def to_dict(self) -> dict:
        return {
            "beat_times": [round(float(x), 4) for x in self.beat_times],
            "beats_per_bar": self.beats_per_bar,
            "compound": self.compound,
            "lead_in": self.lead_in,
            "duration": round(self.duration, 4),
        }

    @classmethod
    def from_dict(cls, d: dict) -> BeatGrid:
        return cls(
            np.asarray(d["beat_times"], dtype=float),
            int(d["beats_per_bar"]),
            bool(d["compound"]),
            int(d["lead_in"]),
            float(d["duration"]),
        )

    def nonnegative(self) -> BeatGrid:
        """Same grid shifted by whole bars so that time 0 has position >= 0."""
        if self.start_position >= -1e-9:
            return self
        bars = int(np.ceil(-self.start_position / self.beats_per_bar - 1e-9))
        return BeatGrid(
            self.beat_times,
            self.beats_per_bar,
            self.compound,
            self.lead_in + bars * self.beats_per_bar,
            self.duration,
        )
