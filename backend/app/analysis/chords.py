"""Chord recognition.

For every beat a 12-bin pitch-class profile (plus a bass profile) is built,
either from transcribed notes (preferred – far cleaner for solo piano) or from
the audio chromagram. Each profile is scored against chord templates for all
12 roots, then a Viterbi pass picks the best path with a penalty for changing
chords, which suppresses flicker from passing tones. Consecutive beats with
the same chord are merged into segments, and slash chords are reported when
the bass is not the root.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.analysis.beatgrid import BeatGrid
from app.analysis.theory import (
    CHORD_QUALITIES,
    ChordQuality,
    KeyInfo,
    chord_label,
    music21_figure,
    nashville_number,
    roman_numeral,
)
from app.analysis.types import Note

NO_CHORD = -1


@dataclass
class ChordSegment:
    start: float
    end: float
    root_pc: int | None  # None = no chord (silence)
    quality: ChordQuality | None
    bass_pc: int | None
    confidence: float
    start_beat: float
    end_beat: float

    def to_dict(self, key: KeyInfo) -> dict:
        if self.root_pc is None or self.quality is None:
            return {
                "start": round(self.start, 3),
                "end": round(self.end, 3),
                "label": "N.C.",
                "root": None,
                "quality": None,
                "bass": None,
                "roman": None,
                "nashville": None,
                "confidence": round(self.confidence, 3),
                "start_beat": round(self.start_beat, 3),
                "end_beat": round(self.end_beat, 3),
            }
        fifths = key.fifths
        return {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "label": chord_label(self.root_pc, self.quality, fifths, self.bass_pc),
            "root": key.spell(self.root_pc),
            "quality": self.quality.suffix,
            "bass": key.spell(self.bass_pc) if self.bass_pc is not None else None,
            "roman": roman_numeral(self.root_pc, self.quality, key, self.bass_pc),
            "nashville": nashville_number(self.root_pc, self.quality, key, self.bass_pc),
            "confidence": round(self.confidence, 3),
            "start_beat": round(self.start_beat, 3),
            "end_beat": round(self.end_beat, 3),
        }

    def music21_figure(self, key: KeyInfo) -> str | None:
        if self.root_pc is None or self.quality is None:
            return None
        return music21_figure(self.root_pc, self.quality, key.fifths, self.bass_pc)


# --- Template scoring -------------------------------------------------------------

_N_Q = len(CHORD_QUALITIES)
# weight matrix W[q, r, pc]: template weights for quality q rooted at r
_W = np.zeros((_N_Q, 12, 12))
_IN = np.zeros((_N_Q, 12, 12), dtype=bool)
for qi, q in enumerate(CHORD_QUALITIES):
    for r in range(12):
        for iv, w in q.tones.items():
            _W[qi, r, (r + iv) % 12] = w
            _IN[qi, r, (r + iv) % 12] = True
_COMPLEXITY = np.array([q.complexity + 0.012 * len(q.tones) for q in CHORD_QUALITIES])
_ESSENTIAL = np.zeros((_N_Q, 12, 12))  # weights >= 0.9 count as essential tones
for qi, q in enumerate(CHORD_QUALITIES):
    for r in range(12):
        for iv, w in q.tones.items():
            if w >= 0.9:
                _ESSENTIAL[qi, r, (r + iv) % 12] = 1.0


def score_profile(pcp: np.ndarray, bass: np.ndarray) -> np.ndarray:
    """Score every (quality, root) for one pitch-class profile.

    ``pcp`` and ``bass`` are non-negative 12-vectors. Returns array [Q, 12].
    """
    total = pcp.sum()
    if total <= 1e-9:
        return np.full((_N_Q, 12), -1.0)
    v = pcp / total
    peak = v.max()
    present = np.clip(v / (0.35 * peak + 1e-9), 0, 1)  # soft "is this pc sounding"

    explained = np.einsum("qrp,p->qr", _W, v)
    extra = np.einsum("qrp,p->qr", ~_IN, v)
    missing = np.einsum("qrp,p->qr", _ESSENTIAL, 1 - present)

    score = explained - 0.9 * extra - 0.12 * missing - _COMPLEXITY[:, None]
    if bass.sum() > 1e-9:
        b = bass / bass.sum()
        # Reward the root being in the bass; a chord tone in the bass is neutral.
        score += 0.18 * b[None, :]
        score -= 0.06 * np.einsum("qrp,p->qr", ~_IN, b)
    return score


# --- Beat-synchronous profiles -----------------------------------------------------


def _beat_edges(grid: BeatGrid, duration: float) -> tuple[np.ndarray, np.ndarray]:
    """Return (analysis edges, reported edges), one entry per beat boundary.

    Analysis windows open slightly before each beat so notes played a hair
    early are counted with the chord they belong to; the reported segment
    boundaries stay on the beats themselves.
    """
    beats = np.asarray(grid.all_beat_times())
    lead = 0.08 * float(np.median(np.diff(beats))) if len(beats) > 1 else 0.0
    beats = beats[(beats - lead > 0.0) & (beats < duration)]
    analysis = np.concatenate([[0.0], beats - lead, [duration]])
    reported = np.concatenate([[0.0], beats, [duration]])
    return analysis, reported


def profiles_from_notes(notes: list[Note], edges: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n_seg = len(edges) - 1
    pcp = np.zeros((n_seg, 12))
    bass = np.zeros((n_seg, 12))
    if not notes:
        return pcp, bass
    starts = np.array([n.start for n in notes])
    ends = np.array([n.end for n in notes])
    for i in range(n_seg):
        a, b = edges[i], edges[i + 1]
        idx = np.nonzero((starts < b) & (ends > a))[0]
        if idx.size == 0:
            continue
        span = b - a
        lowest_pitch = 200
        for k in idx:
            n = notes[k]
            overlap = min(b, n.end) - max(a, n.start)
            w = (overlap / span) * (0.5 + n.velocity / 127)
            if a <= n.start < b:
                w += 0.35 * (0.5 + n.velocity / 127)  # struck in this beat
            pcp[i, n.pitch % 12] += w
            lowest_pitch = min(lowest_pitch, n.pitch)
        # Bass: notes near the lowest sounding pitch.
        for k in idx:
            n = notes[k]
            if n.pitch <= lowest_pitch + 4 and n.pitch < 64:
                overlap = min(b, n.end) - max(a, n.start)
                bass[i, n.pitch % 12] += overlap / span + (0.3 if a <= n.start < b else 0)
    return pcp, bass


def profiles_from_audio(y: np.ndarray, sr: int, edges: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    import librosa

    hop = 512
    y_h = librosa.effects.harmonic(y, margin=2.0)
    chroma = librosa.feature.chroma_cqt(y=y_h, sr=sr, hop_length=hop, fmin=librosa.note_to_hz("C2"), n_octaves=6)
    bass_c = librosa.feature.chroma_cqt(y=y_h, sr=sr, hop_length=hop, fmin=librosa.note_to_hz("C1"), n_octaves=2)
    rms = librosa.feature.rms(y=y_h, hop_length=hop)[0]
    frames = librosa.time_to_frames(edges, sr=sr, hop_length=hop)
    frames = np.clip(frames, 0, chroma.shape[1])
    n_seg = len(edges) - 1
    pcp = np.zeros((n_seg, 12))
    bass = np.zeros((n_seg, 12))
    silence = np.percentile(rms, 10) * 1.5 + 1e-6
    for i in range(n_seg):
        a, b = frames[i], max(frames[i + 1], frames[i] + 1)
        if rms[a:b].mean() < silence:
            continue
        c = chroma[:, a:b].mean(axis=1)
        c = np.clip(c - 0.4 * c.mean(), 0, None)  # suppress the noise floor
        pcp[i] = c
        bc = bass_c[:, a:b].mean(axis=1)
        bass[i] = np.clip(bc - bc.mean(), 0, None)
    return pcp, bass


# --- Decoding -----------------------------------------------------------------------


def _viterbi(scores: np.ndarray, switch_cost: float) -> np.ndarray:
    """scores: [T, S] (higher is better). Returns best state per step."""
    T, S = scores.shape
    dp = scores[0].copy()
    back = np.zeros((T, S), dtype=int)
    for t in range(1, T):
        best_prev = int(np.argmax(dp))
        stay = dp
        switch = dp[best_prev] - switch_cost
        use_switch = switch > stay
        back[t] = np.where(use_switch, best_prev, np.arange(S))
        dp = np.where(use_switch, switch, stay) + scores[t]
    path = np.zeros(T, dtype=int)
    path[-1] = int(np.argmax(dp))
    for t in range(T - 1, 0, -1):
        path[t - 1] = back[t, path[t]]
    return path


def detect_chords(
    pcp: np.ndarray,
    bass: np.ndarray,
    edges: np.ndarray,
    grid: BeatGrid,
    *,
    switch_cost: float = 0.12,
) -> list[ChordSegment]:
    """``edges`` are the reported segment boundaries (len = profiles + 1)."""
    n_seg = len(edges) - 1
    if n_seg == 0:
        return []
    S = _N_Q * 12 + 1  # +1 for "no chord"
    scores = np.zeros((n_seg, S))
    energy = pcp.sum(axis=1)
    thresh = 0.05 * (np.percentile(energy[energy > 0], 90) if (energy > 0).any() else 1.0)
    for i in range(n_seg):
        if energy[i] <= thresh:
            scores[i, :-1] = -1.0
            scores[i, -1] = 0.3
            continue
        s = score_profile(pcp[i], bass[i]).reshape(-1)
        scores[i, :-1] = s
        scores[i, -1] = -0.2
    path = _viterbi(scores, switch_cost)

    segments: list[ChordSegment] = []
    i = 0
    while i < n_seg:
        j = i
        while j + 1 < n_seg and path[j + 1] == path[i]:
            j += 1
        state = int(path[i])
        start, end = float(edges[i]), float(edges[j + 1])
        if state == S - 1:
            seg = ChordSegment(start, end, None, None, None, 1.0, 0, 0)
        else:
            qi, root = divmod(state, 12)
            quality = CHORD_QUALITIES[qi]
            # Confidence: margin of the chosen state over the best alternative.
            seg_scores = scores[i : j + 1, :-1].mean(axis=0)
            chosen = seg_scores[state]
            alt = np.partition(seg_scores, -2)[-2] if seg_scores.max() == chosen else seg_scores.max()
            conf = float(np.clip(0.5 + 4.0 * (chosen - alt), 0.05, 0.99))
            bass_sum = bass[i : j + 1].sum(axis=0)
            bass_pc = int(np.argmax(bass_sum)) if bass_sum.sum() > 0 else None
            # Only call it a slash chord when the bass clearly isn't the root.
            if bass_pc is not None and bass_sum[root] >= 0.6 * bass_sum[bass_pc]:
                bass_pc = root
            seg = ChordSegment(start, end, root, quality, bass_pc, conf, 0, 0)
        seg.start_beat = float(grid.time_to_beat(seg.start))
        seg.end_beat = float(grid.time_to_beat(seg.end))
        segments.append(seg)
        i = j + 1

    # Merge "no chord" gaps shorter than a beat into the previous chord.
    merged: list[ChordSegment] = []
    for seg in segments:
        if merged and seg.root_pc is None and seg.end - seg.start < 0.6 and merged[-1].root_pc is not None:
            merged[-1].end = seg.end
            merged[-1].end_beat = seg.end_beat
            continue
        merged.append(seg)
    return merged


def chords_from_notes(notes: list[Note], grid: BeatGrid, duration: float) -> list[ChordSegment]:
    analysis, reported = _beat_edges(grid, duration)
    pcp, bass = profiles_from_notes(notes, analysis)
    return detect_chords(pcp, bass, reported, grid)


def chords_from_audio(y: np.ndarray, sr: int, grid: BeatGrid, duration: float) -> list[ChordSegment]:
    analysis, reported = _beat_edges(grid, duration)
    pcp, bass = profiles_from_audio(y, sr, analysis)
    return detect_chords(pcp, bass, reported, grid, switch_cost=0.15)
