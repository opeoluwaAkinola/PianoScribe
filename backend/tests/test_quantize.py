from fractions import Fraction

import numpy as np

from app.notation.quantize import QuantizeOptions, TimedNote, grid_costs, quantize_hand, rhythm_evidence

BEAT = 0.6  # seconds per beat (100 BPM)


def tn(pitch, start_beat, dur_beats, vel=80):
    return TimedNote(pitch, vel, start_beat * BEAT, (start_beat + dur_beats) * BEAT, start_beat, start_beat + dur_beats)


def costs_for(notes, compound=False):
    return grid_costs([n.start_beat % 1 for n in notes], compound)


def test_rolled_chord_becomes_one_chord():
    # Four notes spread over ~45 ms, as in a rolled chord.
    notes = [tn(60 + i * 4, 0.02 + i * 0.025, 1.9) for i in range(4)]
    events = quantize_hand(notes)
    assert len(events) == 1
    assert events[0].onset == 0 and events[0].pitches == [60, 64, 68, 72]
    assert events[0].duration == 2


def test_loose_straight_eighths_stay_eighths():
    rng = np.random.default_rng(1)
    notes = [tn(72 + (i % 5), i * 0.5 + rng.normal(0, 0.06), 0.45) for i in range(64)]
    opts = QuantizeOptions(costs=costs_for(notes))
    events = quantize_hand(notes, opts)
    assert len(events) == 64
    assert all(e.onset.denominator in (1, 2) for e in events)  # no 16ths, no triplets
    assert all(e.duration == Fraction(1, 2) for e in events[:-1])


def test_real_triplets_are_detected():
    rng = np.random.default_rng(2)
    notes = [tn(67 + (i % 3), i / 3 + rng.normal(0, 0.02), 0.3) for i in range(48)]
    ev = rhythm_evidence([n.start_beat % 1 for n in notes])
    assert ev["triplet"] > ev["sixteenth"]
    events = quantize_hand(notes, QuantizeOptions(costs=costs_for(notes)))
    assert len(events) == 48
    assert {e.onset.denominator for e in events} <= {1, 3}


def test_detached_stabs_get_clean_rests():
    # Short chords on beats 2 and 4 (backbeat comping).
    notes = [tn(p, b, 0.25) for b in (1, 3, 5, 7) for p in (52, 55, 59)]
    events = quantize_hand(notes)
    assert [e.onset for e in events] == [1, 3, 5, 7]
    # Each stab gets the simplest value on its beat (a quarter) and the rest
    # after it starts on the beat, instead of a fiddly 16th + dotted-8th rest.
    assert all(e.duration == 1 for e in events[:-1])


def test_short_slide_becomes_grace_note():
    notes = [tn(63, 0.95, 0.12), tn(64, 1.08, 0.9), tn(60, 1.08, 0.9)]
    events = quantize_hand(notes)
    assert len(events) == 1
    assert events[0].onset == 1 and events[0].graces == [63] and events[0].pitches == [60, 64]


def test_ghost_notes_are_dropped():
    notes = [tn(60, 0, 1), tn(61, 0.5, 0.05, vel=10)]
    events = quantize_hand(notes)
    assert len(events) == 1 and events[0].pitches == [60]


def test_fixed_grid_is_respected():
    notes = [tn(60, 0.26, 0.2), tn(62, 0.74, 0.2)]
    events = quantize_hand(notes, QuantizeOptions(fixed_grid=2))
    assert all(e.onset.denominator in (1, 2) for e in events)
