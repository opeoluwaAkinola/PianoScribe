"""Synthetic piano test signals (for tests and pipeline smoke checks only).

Renders a known list of notes with a simple additive piano model (inharmonic
partials, pitch-dependent decay, damper release, hammer noise). Because the
ground-truth notes are known, the transcription output can be *measured*
against them instead of eyeballed. Nothing here is used to produce results
for real recordings.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from app.analysis.types import Note


def render_notes(notes: list[Note], sr: int = 44100, tail: float = 1.5, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    total = max((n.end for n in notes), default=0.0) + tail
    out = np.zeros(int(total * sr) + 1, dtype=np.float64)
    for n in notes:
        f0 = 440.0 * 2 ** ((n.pitch - 69) / 12)
        vel = n.velocity / 127
        dur = n.end - n.start
        length = dur + 0.4
        t = np.arange(int(length * sr)) / sr
        tau0 = float(np.clip(3.5 * np.sqrt(110.0 / f0), 0.35, 7.0))
        B = 0.0004 * (f0 / 261.6) ** 0.5
        tone = np.zeros_like(t)
        for k in range(1, 16):
            fk = k * f0 * np.sqrt(1 + B * k * k)
            if fk > 9000:
                break
            ak = (1.0 / k**1.1) * (0.4 + 0.6 * vel) ** (k * 0.35)
            tone += ak * np.exp(-t * (1 + 0.35 * k) / tau0) * np.sin(2 * np.pi * fk * t + rng.uniform(0, 6.28))
        attack = np.clip(t / 0.004, 0, 1)
        release = np.where(t < dur, 1.0, np.exp(-(t - dur) / 0.08))
        env = attack * release
        noise = rng.normal(0, 1, len(t)) * np.exp(-t / 0.01) * 0.05
        sig = (tone * env + noise) * (vel**1.5) * 0.18
        i0 = int(n.start * sr)
        out[i0 : i0 + len(sig)] += sig[: len(out) - i0]
    peak = np.max(np.abs(out)) or 1.0
    return (out / peak * 0.8).astype(np.float32)


def gospel_progression(bpm: float = 76.0, bars: int = 16, seed: int = 1) -> list[Note]:
    """A ii–V–I-flavoured progression in A♭ with a melody, slightly humanised."""
    rng = np.random.default_rng(seed)
    beat = 60.0 / bpm
    # (bass pitch, right-hand chord pitches) per bar: Abmaj9 | Fm9 | Bbm9 | Eb13
    bars_def = [
        (44, [60, 63, 67, 70]),  # Ab: C Eb G Bb  -> Abmaj9 (no root in RH)
        (41, [60, 63, 67, 68]),  # F : C Eb G Ab  -> Fm9
        (46, [61, 65, 68, 72]),  # Bb: Db F Ab C  -> Bbm9
        (39, [61, 65, 67, 72]),  # Eb: Db F G C   -> Eb13
    ]
    melody = [75, 77, 79, 80, 79, 77, 75, 72]
    notes: list[Note] = []
    t0 = 0.5
    for b in range(bars):
        bass, chord = bars_def[b % 4]
        start = t0 + b * 4 * beat
        j = lambda: float(rng.normal(0, 0.008))  # noqa: E731
        notes.append(Note(bass, start + j(), start + 4 * beat - 0.08, 78))
        notes.append(Note(bass + 12, start + 2 * beat + j(), start + 4 * beat - 0.08, 64))
        for p in chord:
            notes.append(Note(p, start + 0.02 + j(), start + 2 * beat - 0.1, 58))
            notes.append(Note(p, start + 2 * beat + 0.02 + j(), start + 4 * beat - 0.1, 54))
        for k in range(4):
            mp = melody[(b * 4 + k) % len(melody)]
            s = start + k * beat + j()
            notes.append(Note(mp, s, s + beat * 0.9, 92))
    notes.sort(key=lambda n: (n.start, n.pitch))
    return notes


def write_wav(path: Path, notes: list[Note], sr: int = 44100) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), render_notes(notes, sr), sr, subtype="PCM_16")
    return path


def onset_f1(ref: list[Note], est: list[Note], tol: float = 0.05) -> dict:
    """Note-level onset precision/recall/F1 (pitch must match, onset within tol)."""
    used = set()
    tp = 0
    est_sorted = sorted(range(len(est)), key=lambda i: est[i].start)
    for r in ref:
        for i in est_sorted:
            if i in used:
                continue
            e = est[i]
            if e.pitch == r.pitch and abs(e.start - r.start) <= tol:
                used.add(i)
                tp += 1
                break
    p = tp / len(est) if est else 0.0
    rcl = tp / len(ref) if ref else 0.0
    f1 = 2 * p * rcl / (p + rcl) if p + rcl else 0.0
    return {
        "precision": round(p, 3),
        "recall": round(rcl, 3),
        "f1": round(f1, 3),
        "tp": tp,
        "ref": len(ref),
        "est": len(est),
    }
