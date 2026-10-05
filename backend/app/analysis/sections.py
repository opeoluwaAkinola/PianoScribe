"""Song-section segmentation.

Beat-synchronous harmony (chroma) and timbre/dynamics (MFCC) features are
segmented with temporally-constrained agglomerative clustering, boundaries are
snapped to bar lines, and segments that sound alike get the same letter
(A, B, A, C…). A short, unique first/last segment is called Intro/Outro.

Naming sections "Verse" or "Chorus" from audio alone would be guesswork, so
we deliberately stick to letters.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.analysis.beatgrid import BeatGrid


@dataclass
class Section:
    start: float
    end: float
    letter: str
    label: str
    start_bar: int
    end_bar: int

    def to_dict(self) -> dict:
        return {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "letter": self.letter,
            "label": self.label,
            "start_bar": self.start_bar + 1,  # 1-based for display
            "end_bar": self.end_bar,
        }


def _label_segments(features: list[np.ndarray], threshold: float = 0.93) -> list[str]:
    letters: list[str] = []
    reps: list[np.ndarray] = []
    for f in features:
        f = f / (np.linalg.norm(f) + 1e-9)
        sims = [float(f @ r) for r in reps]
        if sims and max(sims) >= threshold:
            letters.append(chr(ord("A") + int(np.argmax(sims))))
        else:
            reps.append(f)
            letters.append(chr(ord("A") + len(reps) - 1) if len(reps) <= 26 else "Z")
    return letters


def detect_sections(y: np.ndarray, sr: int, grid: BeatGrid, duration: float) -> list[Section]:
    import librosa

    bars = grid.bar_count()
    if duration < 20 or bars < 6:
        return [Section(0.0, duration, "A", "Section A", 0, bars)]

    hop = 512
    downbeats = np.asarray(grid.downbeat_times())
    bar_edges = np.unique(np.concatenate([[0.0], downbeats[(downbeats > 0) & (downbeats < duration)], [duration]]))
    frames = librosa.time_to_frames(bar_edges, sr=sr, hop_length=hop)

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, hop_length=hop, n_mfcc=13)
    rms = librosa.feature.rms(y=y, hop_length=hop)

    n = min(chroma.shape[1], mfcc.shape[1])
    frames = np.clip(frames, 0, n)
    feats = []
    for a, b in zip(frames[:-1], frames[1:], strict=False):
        b = max(b, a + 1)
        c = chroma[:, a:b].mean(axis=1)
        m = mfcc[1:, a:b].mean(axis=1)
        e = np.log1p(rms[:, a:b].mean(axis=1) * 100)
        feats.append(np.concatenate([c / (np.linalg.norm(c) + 1e-9), m / 50.0, e]))
    X = np.asarray(feats).T  # [dims, bars]
    n_bars = X.shape[1]
    if n_bars < 6:
        return [Section(0.0, duration, "A", "Section A", 0, bars)]

    # Roughly one boundary every ~8 bars or ~25 s, whichever gives fewer.
    k = int(np.clip(min(round(n_bars / 8), round(duration / 25)), 2, 12))
    X_std = (X - X.mean(axis=1, keepdims=True)) / (X.std(axis=1, keepdims=True) + 1e-9)
    # Stack each bar with its neighbours so boundaries prefer real changes.
    X_ctx = np.vstack([X_std, np.roll(X_std, 1, axis=1), np.roll(X_std, -1, axis=1)])
    bounds = librosa.segment.agglomerative(X_ctx, k)
    bounds = sorted(set(int(b) for b in bounds) | {0})

    # Drop segments shorter than 2 bars by merging into the previous one.
    cleaned = [bounds[0]]
    for b in bounds[1:]:
        if b - cleaned[-1] >= 2:
            cleaned.append(b)
    if n_bars - cleaned[-1] < 2 and len(cleaned) > 1:
        cleaned.pop()
    seg_ranges = list(zip(cleaned, cleaned[1:] + [n_bars], strict=False))

    # A quiet, short last/first segment is usually just the piano ringing out
    # (or a breath before playing) – fold it into its neighbour.
    energy = X[-1]
    loud = float(np.median(energy)) or 1e-9
    if len(seg_ranges) > 1:
        a, b = seg_ranges[-1]
        if b - a < 4 and energy[a:b].mean() < 0.6 * loud:
            seg_ranges[-2] = (seg_ranges[-2][0], b)
            seg_ranges.pop()
    if len(seg_ranges) > 1:
        a, b = seg_ranges[0]
        if b - a < 2 and energy[a:b].mean() < 0.6 * loud:
            seg_ranges[1] = (a, seg_ranges[1][1])
            seg_ranges.pop(0)

    seg_feats = [X[:12, a:b].mean(axis=1) for a, b in seg_ranges]  # harmony only for labels
    letters = _label_segments(seg_feats)

    sections: list[Section] = []
    for (a, b), letter in zip(seg_ranges, letters, strict=False):
        start, end = float(bar_edges[a]), float(bar_edges[min(b, len(bar_edges) - 1)])
        sections.append(
            Section(
                start, end, letter, f"Section {letter}", grid.bar_index(start + 1e-3), grid.bar_index(end - 1e-3) + 1
            )
        )

    # Intro / Outro heuristics: short and not repeated elsewhere.
    counts = {lt: letters.count(lt) for lt in letters}
    if len(sections) >= 3:
        first, last = sections[0], sections[-1]
        if counts[first.letter] == 1 and (first.end - first.start) < 0.2 * duration:
            first.label = "Intro"
        if counts[last.letter] == 1 and (last.end - last.start) < 0.2 * duration:
            last.label = "Outro"
    sections[-1].end = duration
    return sections
