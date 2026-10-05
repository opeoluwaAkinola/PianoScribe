import numpy as np

from app.analysis.beatgrid import BeatGrid
from app.analysis.tempo import align_beats_to_onsets, smooth_beats


def test_downbeat_lands_on_bar_line():
    beats = 1.0 + np.arange(16) * 0.5
    g = BeatGrid.from_detection(beats, 4, first_downbeat_index=2, compound=False, duration=10, origin_time=1.0)
    assert g.time_to_beat(beats[2]) % 4 == 0
    assert g.time_to_beat(1.0) >= -0.25  # first event is in bar 1


def test_roundtrip_and_tempo_drift():
    ibis = np.linspace(0.5, 0.6, 20)  # slowing down
    beats = np.concatenate([[0.4], 0.4 + np.cumsum(ibis)])
    g = BeatGrid.from_detection(beats, 3, 0, False, 15, origin_time=0.4)
    t = np.linspace(0, 14, 50)
    assert np.allclose(g.beat_to_time(g.time_to_beat(t)), t, atol=1e-6)
    assert g.time_signature == "3/4"
    assert np.allclose(np.diff(g.time_to_beat(beats)), 1.0)


def test_nonnegative_shift_is_whole_bars():
    beats = 2.0 + np.arange(10) * 0.5
    g = BeatGrid.from_detection(beats, 4, 0, False, 8, origin_time=2.0)
    assert g.start_position < 0
    nn = g.nonnegative()
    assert nn.start_position >= 0
    assert (nn.lead_in - g.lead_in) % 4 == 0


def test_compound_meter():
    g = BeatGrid.from_detection(np.arange(12) * 0.9, 4, 0, True, 11)
    assert g.time_signature == "12/8" and g.beat_ql == 1.5 and g.subdivisions == 3


def test_smoothing_and_alignment():
    rng = np.random.default_rng(0)
    true = 0.3 + np.arange(40) * 0.6
    jittered = true + rng.uniform(-0.012, 0.012, 40) + 0.03  # tracker lag + frame jitter
    sm = smooth_beats(jittered)
    assert np.abs(sm - true - 0.03).max() < np.abs(jittered - true - 0.03).max()
    aligned = align_beats_to_onsets(sm, true)
    assert np.abs(aligned - true).mean() < 0.01
