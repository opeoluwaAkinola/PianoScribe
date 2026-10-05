"""Key estimation (Krumhansl–Schmuckler style profile correlation).

When a transcription is available the pitch-class histogram comes from the
notes (duration and velocity weighted, with extra weight on bass notes, which
strongly signal the tonic). Otherwise it comes from the audio chromagram.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.analysis.theory import KeyInfo
from app.analysis.types import Note

# Krumhansl & Kessler (1982) probe-tone profiles
KK_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KK_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
# Temperley (2007) corpus-derived profiles; averaging the two is more robust.
TP_MAJOR = np.array([0.748, 0.060, 0.488, 0.082, 0.670, 0.460, 0.096, 0.715, 0.104, 0.366, 0.057, 0.400])
TP_MINOR = np.array([0.712, 0.084, 0.474, 0.618, 0.049, 0.460, 0.105, 0.747, 0.404, 0.067, 0.133, 0.330])


@dataclass
class KeyAnalysis:
    key: KeyInfo
    confidence: float
    source: str  # "notes" | "audio" | "override"
    alternatives: list[tuple[KeyInfo, float]]
    histogram: np.ndarray
    scores: list[tuple[KeyInfo, float]] = field(default_factory=list)  # all 24, best first
    refined_by_chords: bool = False

    def to_dict(self) -> dict:
        return {
            "tonic": self.key.tonic,
            "mode": self.key.mode,
            "label": self.key.label,
            "short": self.key.short,
            "fifths": self.key.fifths,
            "confidence": round(float(self.confidence), 3),
            "source": self.source,
            "alternatives": [
                {"label": k.label, "short": k.short, "score": round(float(s), 3)} for k, s in self.alternatives
            ],
            "histogram": [round(float(x), 4) for x in self.histogram],
            "refined_by_chords": self.refined_by_chords,
        }


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    den = np.linalg.norm(a) * np.linalg.norm(b)
    return float(a @ b / den) if den > 0 else 0.0


def key_from_histogram(hist: np.ndarray, source: str) -> KeyAnalysis:
    hist = np.asarray(hist, dtype=float)
    if hist.sum() <= 0:
        return KeyAnalysis(KeyInfo(0, "major"), 0.0, source, [], np.zeros(12))
    hist = hist / hist.sum()
    scores: list[tuple[KeyInfo, float]] = []
    for tonic in range(12):
        rolled = np.roll(hist, -tonic)
        maj = 0.5 * (_corr(rolled, KK_MAJOR) + _corr(rolled, TP_MAJOR))
        mnr = 0.5 * (_corr(rolled, KK_MINOR) + _corr(rolled, TP_MINOR))
        scores.append((KeyInfo(tonic, "major"), maj))
        scores.append((KeyInfo(tonic, "minor"), mnr))
    scores.sort(key=lambda x: x[1], reverse=True)
    best, second = scores[0][1], scores[1][1]
    # Confidence blends absolute fit with the margin over the runner-up.
    confidence = float(np.clip(0.5 * max(best, 0) + 2.5 * (best - second), 0.0, 1.0))
    return KeyAnalysis(scores[0][0], confidence, source, scores[1:4], hist, scores)


def histogram_from_notes(notes: list[Note]) -> np.ndarray:
    hist = np.zeros(12)
    if not notes:
        return hist
    for n in notes:
        hist[n.pitch % 12] += min(n.duration, 2.0) * (0.4 + n.velocity / 127)

    # Bass emphasis: the lowest note of each onset cluster.
    bass = np.zeros(12)
    starts = np.array([n.start for n in notes])
    order = np.argsort(starts)
    i = 0
    while i < len(order):
        j = i
        t0 = starts[order[i]]
        while j < len(order) and starts[order[j]] - t0 < 0.06:
            j += 1
        cluster = [notes[k] for k in order[i:j]]
        low = min(cluster, key=lambda n: n.pitch)
        if low.pitch < 60:
            bass[low.pitch % 12] += min(low.duration, 2.0) + 0.25
        i = j
    if bass.sum() > 0:
        hist = hist / hist.sum() + 0.5 * bass / bass.sum()
    return hist


def histogram_from_audio(y: np.ndarray, sr: int) -> np.ndarray:
    import librosa

    y_h = librosa.effects.harmonic(y, margin=2.0)
    chroma = librosa.feature.chroma_cqt(y=y_h, sr=sr, hop_length=1024)
    bass = librosa.feature.chroma_cqt(y=y_h, sr=sr, hop_length=1024, fmin=librosa.note_to_hz("C1"), n_octaves=3)
    energy = chroma.sum(axis=0)
    active = energy > np.percentile(energy, 20)
    hist = chroma[:, active].mean(axis=1) if active.any() else chroma.mean(axis=1)
    bass_hist = bass[:, active].mean(axis=1) if active.any() else bass.mean(axis=1)
    return hist / (hist.sum() + 1e-9) + 0.4 * bass_hist / (bass_hist.sum() + 1e-9)


def analyze_key_from_notes(notes: list[Note]) -> KeyAnalysis:
    return key_from_histogram(histogram_from_notes(notes), "notes")


def analyze_key_from_audio(y: np.ndarray, sr: int) -> KeyAnalysis:
    return key_from_histogram(histogram_from_audio(y, sr), "audio")


# --- Harmonic refinement -------------------------------------------------------
#
# Pitch-class histograms can't tell A♭ major from E♭ major when a piece leans on
# extended chords (both share most notes). Functional harmony can: in A♭ the
# progression Abmaj9–Fm9–B♭m9–E♭13 is I–vi–ii–V with ii–V–I cadences, in E♭ it
# would be IV–ii–v–I7, which is far less idiomatic. So the top candidates are
# re-ranked by how well the detected chords fit each key.

_FAMILY = {
    "": "maj",
    "maj7": "maj",
    "6": "maj",
    "add9": "maj",
    "maj9": "maj",
    "sus2": "maj",
    "sus4": "maj",
    "7": "dom",
    "9": "dom",
    "11": "dom",
    "13": "dom",
    "7sus4": "dom",
    "m": "min",
    "m7": "min",
    "m9": "min",
    "m11": "min",
    "m6": "min",
    "m7b5": "hdim",
    "dim": "dim",
    "dim7": "dim",
    "aug": "aug",
}
# degree (semitones above tonic) -> {family: fit weight}
_MAJOR_FIT = {
    0: {"maj": 1.0, "dom": 0.5},
    1: {"dom": 0.3, "maj": 0.3},
    2: {"min": 1.0, "dom": 0.6},
    3: {"maj": 0.3, "dim": 0.4},
    4: {"min": 1.0, "dom": 0.6},
    5: {"maj": 1.0, "min": 0.5, "dom": 0.4},
    6: {"dim": 0.6, "hdim": 0.6},
    7: {"dom": 1.0, "maj": 1.0},
    8: {"maj": 0.4, "dom": 0.3},
    9: {"min": 1.0, "dom": 0.6},
    10: {"maj": 0.5, "dom": 0.4},
    11: {"hdim": 1.0, "dim": 0.8, "dom": 0.5},
}
_MINOR_FIT = {
    0: {"min": 1.0, "maj": 0.3},
    1: {"maj": 0.4, "dom": 0.3},
    2: {"hdim": 1.0, "dim": 0.8, "min": 0.4},
    3: {"maj": 1.0},
    5: {"min": 1.0, "dom": 0.4, "maj": 0.3},
    7: {"dom": 1.0, "min": 0.8, "maj": 0.8},
    8: {"maj": 1.0},
    10: {"maj": 1.0, "dom": 0.8},
    11: {"dim": 1.0, "hdim": 0.6},
}


def _harmonic_fit(key: KeyInfo, chords: list[tuple[int, str, float]]) -> float:
    """chords: (root_pc, quality suffix, duration). Returns a score ~0..2."""
    if not chords:
        return 0.0
    table = _MAJOR_FIT if key.mode == "major" else _MINOR_FIT
    total = sum(d for _, _, d in chords) or 1.0
    fit = 0.0
    degs = []
    for root, suffix, dur in chords:
        deg = (root - key.tonic_pc) % 12
        fam = _FAMILY.get(suffix, "maj")
        fit += dur * table.get(deg, {}).get(fam, 0.0)
        degs.append((deg, fam))
    fit /= total

    cadence = 0.0
    for (d1, f1), (d2, f2) in zip(degs, degs[1:], strict=False):
        tonic_fam = "maj" if key.mode == "major" else "min"
        if d2 == 0 and f2 in (tonic_fam, "dom" if key.mode == "major" else tonic_fam):
            if d1 == 7 and f1 in ("dom", "maj"):
                cadence += 1.0  # authentic V–I
            elif d1 == 5:
                cadence += 0.4  # plagal IV–I
            elif d1 == 1 and f1 == "dom":
                cadence += 0.6  # tritone substitute
        if d1 == 2 and d2 == 7 and f2 in ("dom", "maj") and f1 in ("min", "hdim"):
            cadence += 0.5  # ii–V
    cadence /= max(1, len(degs) - 1)

    first_tonic = degs[0][0] == 0
    last_tonic = degs[-1][0] == 0
    return 0.6 * fit + 1.5 * cadence + 0.08 * first_tonic + 0.12 * last_tonic


def refine_key_with_chords(analysis: KeyAnalysis, chords: list[tuple[int, str, float]], top_n: int = 6) -> KeyAnalysis:
    if analysis.source == "override" or not analysis.scores or len(chords) < 3:
        return analysis
    candidates = analysis.scores[:top_n]
    rescored = sorted(
        ((k, corr + _harmonic_fit(k, chords)) for k, corr in candidates), key=lambda x: x[1], reverse=True
    )
    best_key = rescored[0][0]
    margin = rescored[0][1] - rescored[1][1] if len(rescored) > 1 else 0.5
    confidence = float(np.clip(0.4 + 1.5 * margin, 0.05, 0.98))
    alternatives = [(k, s) for k, s in rescored[1:4]]
    return KeyAnalysis(
        best_key,
        confidence,
        analysis.source,
        alternatives,
        analysis.histogram,
        analysis.scores,
        refined_by_chords=best_key != analysis.key,
    )
