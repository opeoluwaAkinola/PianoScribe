"""Generate the frontend's DEVELOPMENT DATA fixture (frontend/public/dev-sample/).

The notes are a hand-written progression (see synth.gospel_progression), *not*
model output. They're rendered to audio with the test synthesiser, then the
real analysis code (tempo, key, chords, sections, MIDI, MusicXML) runs on them
so the UI can be developed against realistic data shapes. The result is
labelled as development data everywhere it appears.

    cd backend && .venv/bin/python -m app.devtools.make_dev_fixture
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import librosa
import numpy as np

from app.analysis.chords import chords_from_notes
from app.analysis.key import analyze_key_from_notes, refine_key_with_chords
from app.analysis.sections import detect_sections
from app.analysis.tempo import align_beats_to_onsets, analyze_tempo
from app.analysis.types import Pedal
from app.config import BACKEND_DIR
from app.devtools.synth import gospel_progression, write_wav
from app.notation.midi import write_midi
from app.notation.musicxml import build_score, write_musicxml
from app.services import media

OUT = BACKEND_DIR.parent / "frontend" / "public" / "dev-sample"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    notes = gospel_progression(bpm=76.0, bars=16, seed=7)
    # Hand-written pedalling: down for each half bar.
    beat = 60 / 76.0
    pedals = [Pedal(0.5 + i * 2 * beat + 0.05, 0.5 + (i + 1) * 2 * beat - 0.03) for i in range(32)]

    with tempfile.TemporaryDirectory() as tmp:
        wav = write_wav(Path(tmp) / "sample.wav", notes)
        media.make_playback_audio(wav, OUT / "audio.m4a")
        y, sr = librosa.load(str(wav), sr=22050, mono=True)

    duration = len(y) / sr
    tempo = analyze_tempo(y, sr)
    tempo.beat_times = align_beats_to_onsets(tempo.beat_times, np.array([n.start for n in notes]))
    grid = tempo.grid(duration, origin_time=notes[0].start)
    key = analyze_key_from_notes(notes)
    chords = chords_from_notes(notes, grid, duration)
    key = refine_key_with_chords(key, [(c.root_pc, c.quality.suffix, c.end - c.start) for c in chords if c.quality])
    sections = detect_sections(y, sr, grid, duration)

    write_midi(OUT / "transcription.mid", notes, pedals, grid, key.key, "Development sample")
    score, info = build_score(notes, grid, key.key, tempo.bpm, chords, "Development sample (synthetic)")
    write_musicxml(OUT / "score.musicxml", score)

    t = tempo.to_dict()
    t.update(
        grid=grid.to_dict(),
        beats=[round(b, 4) for b in grid.all_beat_times()],
        downbeats=[round(b, 4) for b in grid.downbeat_times()],
        start_position=round(grid.start_position, 4),
        bar_count=grid.bar_count(),
        time_signature=grid.time_signature,
    )
    result = {
        "schema_version": 1,
        "development_data": True,
        "analysis_id": "dev-sample",
        "recording_id": "dev-sample",
        "generated_at": "development-fixture",
        "mode": "full",
        "duration": round(duration, 3),
        "transcription": {
            "status": "completed",
            "engine": "development-fixture",
            "engine_label": "Development fixture (hand-written notes)",
            "model": "None – synthetic notes, not a model output",
            "message": None,
            "note_count": len(notes),
            "pedal_count": len(pedals),
            "elapsed_sec": 0,
            "details": {"device": "n/a"},
        },
        "notes": [n.to_dict() for n in notes],
        "pedals": [p.to_dict() for p in pedals],
        "tempo": t,
        "key": key.to_dict(),
        "chords": {"source": "notes", "segments": [c.to_dict(key.key) for c in chords]},
        "sections": [s.to_dict() for s in sections],
        "notation": {
            "measures": info.measures,
            "subdivisions": info.subdivisions,
            "hand_split": info.hand_split,
            "chord_symbols": True,
            "files": {"midi": True, "musicxml": True, "pdf": False},
        },
        "options": {},
        "warnings": ["DEVELOPMENT DATA: synthetic fixture for UI work – not a transcription of a real recording."],
    }
    (OUT / "result.json").write_text(json.dumps(result, separators=(",", ":")))
    (OUT / "README.md").write_text(
        "# Development data\n\nSynthetic fixture for UI development only (hand-written notes rendered with a test "
        "synthesiser). Not a transcription of any recording. Regenerate with:\n\n"
        "    cd backend && .venv/bin/python -m app.devtools.make_dev_fixture\n"
    )
    print(f"Wrote development fixture to {OUT}")
    print(
        f"  key={key.key.label} bpm={tempo.bpm:.1f} ts={grid.time_signature} bars={grid.bar_count()} "
        f"chords={len(chords)} sections={len(sections)}"
    )


if __name__ == "__main__":
    main()
