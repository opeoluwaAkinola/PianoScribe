import numpy as np

from app.analysis.beatgrid import BeatGrid
from app.analysis.theory import KeyInfo
from app.analysis.types import Note, Pedal
from app.notation.midi import read_midi_notes, write_midi
from app.notation.musicxml import build_score, write_musicxml


def _notes():
    rng = np.random.default_rng(3)
    beats = 0.7 + np.cumsum(np.full(32, 0.75) + rng.normal(0, 0.01, 32))
    notes = []
    for i, b in enumerate(beats[:-1]):
        notes.append(Note(72 + (i % 5), float(b), float(b) + 0.5, 90))
        if i % 4 == 0:
            notes += [Note(p, float(b), float(beats[min(i + 4, 31)]) - 0.05, 60) for p in (44, 51, 60, 63)]
    return notes, beats


def test_midi_preserves_performance_timing(tmp_path):
    notes, beats = _notes()
    grid = BeatGrid.from_detection(beats, 4, 1, False, float(beats[-1]) + 1, origin_time=0.7)
    path = tmp_path / "t.mid"
    write_midi(path, notes, [Pedal(1.0, 2.0)], grid, KeyInfo(8, "major"), "Test")
    back, pedals = read_midi_notes(path)
    assert len(back) == len(notes)
    ref = sorted(notes, key=lambda n: (n.start, n.pitch))
    err = max(abs(a.start - b.start) for a, b in zip(ref, back, strict=True))
    assert err < 0.002  # within 2 ms of the audio
    assert len(pedals) == 1


def test_musicxml_is_valid_and_keyed(tmp_path):
    from music21 import converter

    notes, beats = _notes()
    grid = BeatGrid.from_detection(beats, 4, 0, False, float(beats[-1]) + 1, origin_time=0.7)
    score, info = build_score(notes, grid, KeyInfo(8, "major"), 80, [], "Test")
    path = tmp_path / "t.musicxml"
    write_musicxml(path, score)
    parsed = converter.parse(str(path))
    assert info.measures >= 8
    ks = parsed.recurse().getElementsByClass("KeySignature").first()
    assert ks is not None and ks.sharps == -4
    pitches = {p.name for p in parsed.recurse().pitches}
    assert "D-" not in pitches or "C#" not in pitches  # consistent flat spelling
    assert "E-" in pitches and "A-" in pitches


def test_midi_accepts_unicode_titles(tmp_path):
    notes, beats = _notes()
    grid = BeatGrid.from_detection(beats, 4, 0, False, float(beats[-1]) + 1)
    path = tmp_path / "u.mid"
    write_midi(path, notes, [], grid, KeyInfo(8, "major"), "Sunday ballad – ii–V–I in A♭ ♯ “live” 日本")
    import mido

    name = next(m.name for m in mido.MidiFile(str(path)).tracks[0] if m.type == "track_name")
    assert name.startswith("Sunday ballad - ii-V-I in Ab #")
