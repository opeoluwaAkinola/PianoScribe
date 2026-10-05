"""Tempo, beat and meter estimation from audio (librosa signal processing).

* Beats: librosa's dynamic-programming beat tracker on the onset envelope.
* BPM: median inter-beat interval (robust to rubato at the edges).
* Meter: which grouping (3 or 4) best explains periodic accents, where an
  accent combines onset strength, bass onsets and harmonic change (chords and
  bass notes tend to change on downbeats).
* Compound feel (12/8): whether beats are subdivided into threes rather than
  twos, a common feel in slow gospel ballads.

These are heuristics and are reported with a confidence value; the UI lets
you override the result and re-engrave.
"""

from __future__ import annotations

from dataclasses import dataclass

import librosa
import numpy as np

from app.analysis.beatgrid import BeatGrid

HOP = 512


@dataclass
class TempoAnalysis:
    bpm: float
    beat_times: np.ndarray
    beats_per_bar: int
    compound: bool
    first_downbeat_index: int
    meter_confidence: float
    triplet_ratio: float
    stability: float  # coefficient of variation of inter-beat intervals (0 = metronomic)
    accents: np.ndarray  # per-beat accent strength (z-scored), used for re-phasing
    fallback: bool = False

    @property
    def time_signature(self) -> str:
        return f"{self.beats_per_bar * 3}/8" if self.compound else f"{self.beats_per_bar}/4"

    def grid(self, duration: float, origin_time: float = 0.0) -> BeatGrid:
        if self.fallback or len(self.beat_times) < 2:
            return BeatGrid.constant(self.bpm or 120.0, duration, self.beats_per_bar, self.compound)
        return BeatGrid.from_detection(
            self.beat_times,
            self.beats_per_bar,
            self.first_downbeat_index,
            self.compound,
            duration,
            origin_time=origin_time,
        )

    def tempo_curve(self) -> list[dict]:
        bt = self.beat_times
        if len(bt) < 3:
            return []
        ibi = np.diff(bt)
        local = 60.0 / ibi
        k = min(7, len(local) // 2 * 2 + 1)
        if k >= 3:
            from scipy.signal import medfilt

            local = medfilt(local, kernel_size=k)
        mids = (bt[:-1] + bt[1:]) / 2
        step = max(1, len(mids) // 400)  # keep the payload small
        return [
            {"time": round(float(t), 3), "bpm": round(float(b), 2)}
            for t, b in zip(mids[::step], local[::step], strict=False)
        ]

    def to_dict(self) -> dict:
        return {
            "bpm": round(float(self.bpm), 2),
            "time_signature": self.time_signature,
            "beats_per_bar": self.beats_per_bar,
            "compound": self.compound,
            "first_downbeat_index": int(self.first_downbeat_index),
            "meter_confidence": round(float(self.meter_confidence), 3),
            "triplet_ratio": round(float(self.triplet_ratio), 3),
            "stability": round(float(self.stability), 4),
            "beat_count": int(len(self.beat_times)),
            "fallback": self.fallback,
            "accents": [round(float(a), 3) for a in self.accents],
            "tempo_curve": self.tempo_curve(),
        }


def _zscore(x: np.ndarray) -> np.ndarray:
    sd = float(np.std(x))
    return (x - float(np.mean(x))) / sd if sd > 1e-9 else np.zeros_like(x)


def _peak_at(env: np.ndarray, frames: np.ndarray, radius: int = 2) -> np.ndarray:
    out = np.zeros(len(frames))
    for i, f in enumerate(frames):
        lo, hi = max(0, int(f) - radius), min(len(env), int(f) + radius + 1)
        out[i] = env[lo:hi].max() if hi > lo else 0.0
    return out


def smooth_beats(beat_times: np.ndarray, half_window: int = 2) -> np.ndarray:
    """Remove frame-quantisation jitter while keeping genuine tempo drift.

    Each beat is replaced by a local linear fit over its neighbours.
    """
    bt = np.asarray(beat_times, dtype=float)
    n = len(bt)
    if n < 2 * half_window + 1:
        return bt
    out = bt.copy()
    idx = np.arange(n)
    for i in range(n):
        lo, hi = max(0, i - half_window), min(n, i + half_window + 1)
        slope, intercept = np.polyfit(idx[lo:hi], bt[lo:hi], 1)
        out[i] = slope * i + intercept
    # Keep strictly increasing (safety for extreme rubato).
    return np.maximum.accumulate(out + np.arange(n) * 1e-6)


def align_beats_to_onsets(beat_times: np.ndarray, onsets: np.ndarray, max_shift: float = 0.06) -> np.ndarray:
    """Shift the beat grid by the median lag between beats and nearby note onsets.

    Onset-envelope beat trackers tend to place beats a few tens of milliseconds
    after the actual key strikes; transcribed onsets are much more precise.
    """
    bt = np.asarray(beat_times, dtype=float)
    if len(bt) < 4 or len(onsets) == 0:
        return bt
    ibi = float(np.median(np.diff(bt)))
    on = np.sort(np.asarray(onsets, dtype=float))
    j = np.clip(np.searchsorted(on, bt), 1, len(on) - 1)
    nearest = np.where(np.abs(on[j] - bt) < np.abs(on[j - 1] - bt), on[j], on[j - 1])
    diffs = nearest - bt
    close = np.abs(diffs) < 0.15 * ibi
    if close.sum() < max(3, 0.2 * len(bt)):
        return bt
    shift = float(np.clip(np.median(diffs[close]), -max_shift, max_shift))
    return bt + shift


def best_phase(accents: np.ndarray, beats_per_bar: int) -> tuple[int, float]:
    """Return (phase, contrast): which beat index mod N carries the downbeat."""
    if len(accents) < beats_per_bar * 2:
        return 0, 0.0
    best = (0, -np.inf)
    for p in range(beats_per_bar):
        on = accents[p::beats_per_bar]
        mask = np.ones(len(accents), dtype=bool)
        mask[p::beats_per_bar] = False
        contrast = float(on.mean() - accents[mask].mean())
        if contrast > best[1]:
            best = (p, contrast)
    return best


def _beat_accents(y: np.ndarray, sr: int, beats: np.ndarray, oenv: np.ndarray) -> np.ndarray:
    onset_acc = _peak_at(oenv, beats)

    mel = librosa.feature.melspectrogram(y=y, sr=sr, hop_length=HOP, n_mels=96, fmax=8000)
    mel_freqs = librosa.mel_frequencies(n_mels=96, fmax=8000)
    low = mel_freqs < 200
    bass_env = librosa.onset.onset_strength(S=librosa.power_to_db(mel[low]), sr=sr, hop_length=HOP)
    bass_acc = _peak_at(bass_env, beats)

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=HOP)
    sync = librosa.util.sync(chroma, beats, aggregate=np.median)
    # sync has one column per inter-beat segment (plus the leading segment).
    sync = sync[:, 1 : len(beats) + 1] if sync.shape[1] > len(beats) else sync
    norm = sync / (np.linalg.norm(sync, axis=0, keepdims=True) + 1e-9)
    change = np.zeros(len(beats))
    if norm.shape[1] > 1:
        cos = np.sum(norm[:, 1:] * norm[:, :-1], axis=0)
        change[1 : 1 + len(cos)] = 1 - cos[: len(beats) - 1]

    return 0.8 * _zscore(onset_acc) + 1.0 * _zscore(bass_acc) + 1.2 * _zscore(change)


def _triplet_ratio(oenv: np.ndarray, beats: np.ndarray) -> float:
    def pick(a: int, span: int, frac: float) -> float:
        c = int(round(a + frac * span))
        return float(oenv[c - 1 : c + 2].max())

    half, thirds = [], []
    for a, b in zip(beats[:-1], beats[1:], strict=False):
        span = b - a
        if span < 6:
            continue
        half.append(pick(a, span, 0.5))
        thirds.append(max(pick(a, span, 1 / 3), pick(a, span, 2 / 3)))
    if not half:
        return 1.0
    return float((np.mean(thirds) + 1e-6) / (np.mean(half) + 1e-6))


def analyze_tempo(
    y: np.ndarray,
    sr: int,
    *,
    bpm_hint: float | None = None,
    meter_override: tuple[int, bool] | None = None,
) -> TempoAnalysis:
    oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP, aggregate=np.median)
    kwargs: dict = {"start_bpm": 100.0}
    if bpm_hint:
        kwargs = {"bpm": float(bpm_hint), "tightness": 400}
    tempo, beats = librosa.beat.beat_track(
        onset_envelope=oenv, sr=sr, hop_length=HOP, units="frames", trim=True, **kwargs
    )
    beats = np.asarray(beats, dtype=int)
    beat_times = librosa.frames_to_time(beats, sr=sr, hop_length=HOP)

    if len(beat_times) < 4:
        bpm = float(np.atleast_1d(tempo)[0]) if np.atleast_1d(tempo).size else 0.0
        bpm = bpm_hint or (bpm if 30 < bpm < 300 else 120.0)
        bpb, comp = meter_override or (4, False)
        return TempoAnalysis(
            bpm=bpm,
            beat_times=np.asarray([]),
            beats_per_bar=bpb,
            compound=comp,
            first_downbeat_index=0,
            meter_confidence=0.0,
            triplet_ratio=1.0,
            stability=1.0,
            accents=np.asarray([]),
            fallback=True,
        )

    beat_times = smooth_beats(beat_times)
    ibi = np.diff(beat_times)
    bpm = 60.0 / float(np.median(ibi))
    stability = float(np.std(ibi) / np.mean(ibi))

    accents = _beat_accents(y, sr, beats, oenv)
    triplet_ratio = _triplet_ratio(oenv, beats)

    phase3, c3 = best_phase(accents, 3)
    phase4, c4 = best_phase(accents, 4)

    if meter_override:
        bpb, compound = meter_override
        phase, contrast = best_phase(accents, bpb)
        confidence = 1.0
    else:
        if c3 > c4 + 0.15 and c3 > 0.25:
            bpb, phase, contrast, other = 3, phase3, c3, c4
        else:
            bpb, phase, contrast, other = 4, phase4, c4, c3
        compound = bpb == 4 and triplet_ratio > 1.25 and bpm < 100
        margin = contrast - other
        confidence = float(np.clip(0.35 + 0.5 * margin + 0.3 * contrast, 0.05, 0.95))

    return TempoAnalysis(
        bpm=bpm,
        beat_times=beat_times,
        beats_per_bar=bpb,
        compound=compound,
        first_downbeat_index=phase,
        meter_confidence=confidence,
        triplet_ratio=triplet_ratio,
        stability=stability,
        accents=accents,
    )
