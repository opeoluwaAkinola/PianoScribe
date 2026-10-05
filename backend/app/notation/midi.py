"""MIDI export.

The file keeps the performance's exact timing (a note at 12.34 s in the audio
plays at 12.34 s in the MIDI) *and* carries a tempo map that follows the
detected beats, so bar lines in a DAW or notation program line up with the
music instead of drifting.
"""

from __future__ import annotations

from pathlib import Path

import mido
import numpy as np

from app.analysis.beatgrid import BeatGrid
from app.analysis.theory import KeyInfo
from app.analysis.types import Note, Pedal

TPQ = 480  # ticks per quarter note
# The (fractional) pickup before time 0 is squeezed into a very fast tempo so
# audio time 0 is (almost exactly) MIDI time 0.
_LEAD_US_PER_QUARTER = 2000


_TRANSLITERATE = str.maketrans(
    {"♭": "b", "♯": "#", "♮": "", "–": "-", "—": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "…": "..."}
)


def _midi_text(text: str) -> str:
    """MIDI text events are Latin-1; keep what we can and replace the rest."""
    return text.translate(_TRANSLITERATE).encode("latin-1", errors="replace").decode("latin-1")[:120]


def _tempo_map(grid: BeatGrid) -> tuple[np.ndarray, np.ndarray]:
    """Return breakpoints (seconds, quarter-note position)."""
    times, beats = grid.nonnegative().anchors()
    qpos = beats * grid.beat_ql
    secs = times.astype(float).copy()
    lead_q = float(qpos[0])
    if lead_q > 1e-6:
        lead_sec = lead_q * _LEAD_US_PER_QUARTER / 1e6
        secs = np.concatenate([[0.0], np.maximum(secs[:1], lead_sec), secs[1:]])
        qpos = np.concatenate([[0.0], qpos])
    return secs, qpos


def write_midi(
    path: Path,
    notes: list[Note],
    pedals: list[Pedal],
    grid: BeatGrid,
    key: KeyInfo | None,
    title: str = "PianoScribe transcription",
) -> None:
    secs, qpos = _tempo_map(grid)

    def tick(t: float) -> int:
        return max(0, int(round(float(np.interp(t, secs, qpos)) * TPQ)))

    mid = mido.MidiFile(type=1, ticks_per_beat=TPQ)
    meta: list[tuple[int, int, mido.Message | mido.MetaMessage]] = []
    meta.append((0, 0, mido.MetaMessage("track_name", name=_midi_text(title))))
    num, den = (grid.beats_per_bar * 3, 8) if grid.compound else (grid.beats_per_bar, 4)
    meta.append(
        (
            0,
            1,
            mido.MetaMessage(
                "time_signature", numerator=num, denominator=den, clocks_per_click=36 if grid.compound else 24
            ),
        )
    )
    if key is not None:
        try:
            meta.append((0, 2, mido.MetaMessage("key_signature", key=key.mido_name)))
        except Exception:  # pragma: no cover - mido rejects unusual spellings
            pass

    ticks = np.round(qpos * TPQ).astype(int)
    last_tempo = None
    for i in range(len(ticks) - 1):
        span = ticks[i + 1] - ticks[i]
        if span <= 0:
            continue
        us = int(round((secs[i + 1] - secs[i]) / (span / TPQ) * 1e6))
        us = int(np.clip(us, 1, 16_777_215))
        if us != last_tempo:
            meta.append((int(ticks[i]), 3, mido.MetaMessage("set_tempo", tempo=us)))
            last_tempo = us

    events: list[tuple[int, int, mido.Message | mido.MetaMessage]] = [
        (0, 0, mido.MetaMessage("track_name", name="Piano")),
        (0, 1, mido.Message("program_change", program=0, channel=0)),
    ]
    # Avoid a note-off cutting off a re-struck note of the same pitch.
    by_pitch: dict[int, list[Note]] = {}
    for n in notes:
        by_pitch.setdefault(n.pitch, []).append(n)
    for same in by_pitch.values():
        same.sort(key=lambda n: n.start)
        for i, n in enumerate(same):
            end = n.end if i + 1 == len(same) else min(n.end, same[i + 1].start)
            on, off = tick(n.start), tick(end)
            if off <= on:
                off = on + 1
            # sort key: offs (2) before ons (3) at the same tick
            events.append((on, 3, mido.Message("note_on", note=n.pitch, velocity=n.velocity, channel=0)))
            events.append((off, 2, mido.Message("note_off", note=n.pitch, velocity=0, channel=0)))
    for p in pedals:
        events.append((tick(p.start), 1, mido.Message("control_change", control=64, value=127, channel=0)))
        events.append((tick(p.end), 1, mido.Message("control_change", control=64, value=0, channel=0)))

    for evs in (meta, events):
        track = mido.MidiTrack()
        evs.sort(key=lambda e: (e[0], e[1]))
        cur = 0
        for t, _, msg in evs:
            track.append(msg.copy(time=t - cur))
            cur = t
        track.append(mido.MetaMessage("end_of_track", time=0))
        mid.tracks.append(track)

    path.parent.mkdir(parents=True, exist_ok=True)
    mid.save(str(path))


def read_midi_notes(path: Path) -> tuple[list[Note], list[Pedal]]:
    """Parse notes and sustain pedal from any MIDI file (absolute seconds)."""
    mid = mido.MidiFile(str(path))
    notes: list[Note] = []
    pedals: list[Pedal] = []
    active: dict[tuple[int, int], list[tuple[float, int]]] = {}
    pedal_on: dict[int, float] = {}
    t = 0.0
    for msg in mid:  # iterating a MidiFile yields messages with time in seconds
        t += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            active.setdefault((msg.channel, msg.note), []).append((t, msg.velocity))
        elif msg.type in ("note_off", "note_on"):
            stack = active.get((msg.channel, msg.note))
            if stack:
                start, vel = stack.pop(0)
                if t > start:
                    notes.append(Note(msg.note, start, t, vel))
        elif msg.type == "control_change" and msg.control == 64:
            if msg.value >= 64 and msg.channel not in pedal_on:
                pedal_on[msg.channel] = t
            elif msg.value < 64 and msg.channel in pedal_on:
                start = pedal_on.pop(msg.channel)
                if t > start:
                    pedals.append(Pedal(start, t))
    notes.sort(key=lambda n: (n.start, n.pitch))
    pedals.sort(key=lambda p: p.start)
    return notes, pedals
