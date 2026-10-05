import numpy as np
import pytest

from app.analysis.beatgrid import BeatGrid
from app.analysis.chords import chords_from_notes, score_profile
from app.analysis.key import analyze_key_from_notes, refine_key_with_chords
from app.analysis.theory import CHORD_QUALITIES, spell_pc
from app.analysis.types import Note


def best(pcs, bass=None):
    v = np.zeros(12)
    for p in pcs:
        v[p % 12] += 1
    b = np.zeros(12)
    if bass is not None:
        b[bass % 12] = 1
    i = int(np.argmax(score_profile(v, b)))
    return spell_pc(i % 12, -1) + CHORD_QUALITIES[i // 12].suffix


@pytest.mark.parametrize(
    ("pcs", "bass", "expected"),
    [
        ([0, 4, 7], 0, "C"),
        ([0, 3, 7], 0, "Cm"),
        ([0, 4, 7, 11], 0, "Cmaj7"),
        ([2, 5, 9, 0], 2, "Dm7"),
        ([7, 11, 2, 5], 7, "G7"),
        ([0, 4, 7, 10, 2], 0, "C9"),
        ([11, 2, 5, 9], 11, "Bm7b5"),
        ([7, 11, 5, 4], 7, "G13"),
        ([7, 10, 1, 4], 7, "Gdim7"),
        ([10, 2, 5], 0, "C11"),
        ([0, 5, 7], 0, "Csus4"),
    ],
)
def test_template_matching(pcs, bass, expected):
    assert best(pcs, bass) == expected


def _progression(bars_def, bpm=80.0, repeats=3):
    beat = 60 / bpm
    notes = []
    for r in range(repeats):
        for b, (bass, chord) in enumerate(bars_def):
            t = 0.5 + (r * len(bars_def) + b) * 4 * beat
            notes.append(Note(bass, t, t + 4 * beat - 0.05, 80))
            notes += [Note(p, t + 0.01, t + 4 * beat - 0.1, 60) for p in chord]
    n_beats = repeats * len(bars_def) * 4
    beats = 0.5 + np.arange(n_beats) * beat
    return notes, beats, beats[-1] + beat


def test_progression_and_key_refinement():
    # Abmaj9 | Fm9 | Bbm9 | Eb13  (rootless right-hand voicings)
    bars = [(44, [60, 63, 67, 70]), (41, [60, 63, 67, 68]), (46, [61, 65, 68, 72]), (39, [61, 65, 67, 72])]
    notes, beats, dur = _progression(bars)
    grid = BeatGrid.from_detection(beats, 4, 0, False, dur, origin_time=0.5)
    chords = chords_from_notes(notes, grid, dur)
    key = analyze_key_from_notes(notes)
    key = refine_key_with_chords(key, [(c.root_pc, c.quality.suffix, c.end - c.start) for c in chords if c.quality])
    assert key.key.label == "A♭ major"
    labels = [c.to_dict(key.key)["label"] for c in chords if c.root_pc is not None]
    assert labels[:4] == ["Abmaj9", "Fm9", "Bbm9", "Eb13"]
    romans = [c.to_dict(key.key)["roman"] for c in chords if c.root_pc is not None][:4]
    assert romans == ["Imaj9", "vi9", "ii9", "V13"]
    # Chord changes are reported on the bar lines, not slightly before them.
    starts = [c.start_beat for c in chords if c.root_pc is not None][:4]
    assert np.allclose(starts, [0, 4, 8, 12], atol=0.02)


def test_silence_is_no_chord():
    notes, beats, dur = _progression([(48, [60, 64, 67])], repeats=1)
    grid = BeatGrid.from_detection(np.concatenate([beats, beats[-1] + 0.75 * np.arange(1, 9)]), 4, 0, False, dur + 6)
    chords = chords_from_notes(notes, grid, dur + 6)
    assert chords[-1].root_pc is None
