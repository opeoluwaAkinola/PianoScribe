"""MusicXML engraving with music21.

Turning a performance into readable notation means simplifying it:

1. Note times are converted to beat positions with the BeatGrid (so tempo
   drift doesn't wreck the barlines).
2. Notes are split between hands at a pitch threshold (middle C by default).
3. Each hand is quantised by ``quantize.py``: chords are clustered, ornaments
   become grace notes and every beat picks its simplest fitting grid (quarter,
   8ths, 16ths or triplets). Each chord lasts until the next onset unless
   there's a clear gap, which yields one clean voice per staff.
4. Detected chord symbols are written above the treble staff.

The raw, unquantised performance is always available in the MIDI file.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from app.analysis.beatgrid import BeatGrid
from app.analysis.chords import ChordSegment
from app.analysis.theory import KeyInfo
from app.analysis.types import Note
from app.notation.quantize import QuantizeOptions, TimedNote, grid_costs, quantize_hand


@dataclass
class NotationOptions:
    hand_split: int = 60  # MIDI pitch; notes >= split go to the right hand
    subdivisions: int | None = None  # force steps per beat (None = adaptive per beat)
    chord_symbols: bool = True
    min_note_sec: float = 0.035  # drop ghost notes shorter than this


@dataclass
class NotationResult:
    measures: int
    subdivisions: int | None  # None = adaptive
    hand_split: int


def _spell(pitch_obj, prefer_flats: bool, prefer_sharps: bool):
    acc = pitch_obj.accidental
    if acc is None:
        return pitch_obj
    if prefer_flats and acc.name == "sharp":
        return pitch_obj.getEnharmonic()
    if prefer_sharps and acc.name == "flat":
        return pitch_obj.getEnharmonic()
    return pitch_obj


def build_score(
    notes: list[Note],
    grid: BeatGrid,
    key: KeyInfo,
    bpm: float,
    chords: list[ChordSegment] | None = None,
    title: str = "Transcription",
    options: NotationOptions | None = None,
):
    from music21 import chord as m21chord
    from music21 import clef, harmony, instrument, layout, metadata, meter, stream, tempo
    from music21 import key as m21key
    from music21 import note as m21note
    from music21 import pitch as m21pitch

    opts = options or NotationOptions()
    prefer_flats = key.fifths < 0
    prefer_sharps = key.fifths > 0
    bpb = grid.beats_per_bar
    beat_ql = Fraction(3, 2) if grid.compound else Fraction(1)
    bars = max(1, math.ceil(float(grid.time_to_beat(grid.duration)) / bpb - 1e-6))
    end_beats = Fraction(bars * bpb)
    playable = [n for n in notes if n.end - n.start >= opts.min_note_sec]
    beat_pos = [float(b) for b in grid.time_to_beat([n.start for n in playable])] if playable else []
    costs = grid_costs([b - math.floor(b) for b in beat_pos], grid.compound)
    qopts = QuantizeOptions(compound=grid.compound, fixed_grid=opts.subdivisions, costs=costs)

    def make_pitch(midi: int):
        p = m21pitch.Pitch(midi=midi)
        return _spell(p, prefer_flats, prefer_sharps)

    rh = stream.PartStaff(id="RH")
    lh = stream.PartStaff(id="LH")
    for part, cl in ((rh, clef.TrebleClef()), (lh, clef.BassClef())):
        part.insert(0, instrument.Piano())
        part.insert(0, cl)
        part.insert(0, m21key.Key(key.music21_name))
        part.insert(0, meter.TimeSignature(grid.time_signature))

    referent = m21note.Note(type="quarter", dots=1) if grid.compound else m21note.Note(type="quarter")
    rh.insert(0, tempo.MetronomeMark(number=int(round(bpm)), referent=referent.duration))

    for part, in_hand in (
        (rh, lambda n: n.pitch >= opts.hand_split),
        (lh, lambda n: n.pitch < opts.hand_split),
    ):
        timed = [
            TimedNote(
                n.pitch, n.velocity, n.start, n.end, float(grid.time_to_beat(n.start)), float(grid.time_to_beat(n.end))
            )
            for n in playable
            if in_hand(n)
        ]
        for ev in quantize_hand(timed, qopts):
            if ev.onset >= end_beats:
                continue
            offset = ev.onset * beat_ql
            for gp in ev.graces:
                part.insert(offset, m21note.Note(make_pitch(gp)).getGrace())
            if len(ev.pitches) == 1:
                el = m21note.Note(make_pitch(ev.pitches[0]))
            else:
                el = m21chord.Chord([make_pitch(p) for p in ev.pitches])
            el.quarterLength = min(ev.duration, end_beats - ev.onset) * beat_ql
            part.insert(offset, el)

    if opts.chord_symbols and chords:
        used: set[float] = set()
        for seg in chords:
            fig = seg.music21_figure(key)
            if not fig:
                continue
            # Snap chord symbols to the nearest half beat.
            off = round(float(grid.time_to_beat(seg.start)) * 2) / 2 * grid.beat_ql
            if off < 0 or off >= float(end_beats * beat_ql) or off in used:
                continue
            try:
                cs = harmony.ChordSymbol(fig)
            except Exception:
                continue
            cs.writeAsChord = False
            used.add(off)
            rh.insert(off, cs)

    score = stream.Score(id="PianoScribe")
    score.metadata = metadata.Metadata()
    score.metadata.title = title
    score.metadata.composer = "Transcribed by PianoScribe AI"

    end_ql = float(end_beats * beat_ql)
    for part in (rh, lh):
        part.makeRests(refStreamOrTimeRange=[0.0, end_ql], fillGaps=True, inPlace=True, hideRests=False)
        part.makeNotation(inPlace=True)
        score.insert(0, part)
    score.insert(0, layout.StaffGroup([rh, lh], name="Piano", abbreviation="Pno.", symbol="brace"))
    return score, NotationResult(measures=bars, subdivisions=opts.subdivisions, hand_split=opts.hand_split)


def write_musicxml(path: Path, score) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.musicxml")
    score.write("musicxml", fp=str(tmp))
    # music21 writes the title as both <work-title> and <movement-title>, which
    # renderers show as a duplicated title + subtitle. Keep the movement title.
    xml = tmp.read_text(encoding="utf-8")
    xml = re.sub(r"\s*<work>.*?</work>", "", xml, count=1, flags=re.S)
    tmp.write_text(xml, encoding="utf-8")
    tmp.replace(path)
