"""Command-line utilities.

python -m app.cli doctor             # check ffmpeg, engines, MuseScore, worker
python -m app.cli download-models    # fetch the ByteDance checkpoint now
python -m app.cli transcribe FILE    # run the full pipeline on a file, no UI
python -m app.cli make-test-audio    # write a synthetic piano WAV with known notes
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def cmd_doctor(_args) -> int:
    from app.config import get_settings
    from app.db import SessionLocal, init_db
    from app.notation.pdf import find_musescore
    from app.services import jobs, media
    from app.transcription.registry import describe_engines

    s = get_settings()
    s.ensure_dirs()
    init_db()
    ok = True
    print(f"Data directory : {s.data_dir}")
    ff = media.find_ffmpeg()
    print(f"ffmpeg         : {ff or 'NOT FOUND'} {media.ffmpeg_version() or ''}")
    ok &= bool(ff)
    print(f"MuseScore (PDF): {find_musescore() or 'not installed (optional – browser printing still works)'}")
    print(f"Torch device   : {s.torch_device}")
    print("Transcription engines:")
    for e in describe_engines(s):
        mark = "✔" if e["available"] else "✘"
        default = " (default)" if e["is_default"] else ""
        print(f"  {mark} {e['id']}{default}: {e['label']}")
        if e["reason"]:
            print(f"      {e['reason']}")
        if e["install_hint"]:
            print(f"      → {e['install_hint']}")
    with SessionLocal() as db:
        workers = jobs.live_workers(db)
    print(f"Workers online : {len(workers)}" + ("" if workers else "  (start one with: python -m app.worker)"))
    return 0 if ok else 1


def cmd_download_models(_args) -> int:
    from app.config import get_settings
    from app.transcription.bytedance import download_checkpoint

    s = get_settings()
    s.ensure_dirs()
    last = [-1]

    def progress(f: float, msg: str | None) -> None:
        pct = int(f * 100)
        if pct != last[0]:
            last[0] = pct
            print(f"\r{msg or ''} ({pct}%)", end="", flush=True)

    path = download_checkpoint(s, progress)
    print(f"\nCheckpoint ready: {path}")
    return 0


def cmd_transcribe(args) -> int:
    """Upload-free path: register the file, run the pipeline inline, print a summary."""
    from app.config import get_settings
    from app.db import init_db, session_scope
    from app.models import Recording, new_id
    from app.pipeline.runner import Pipeline
    from app.services import jobs, media
    from app.services.storage import LocalStorage
    from app.transcription.registry import default_engine_id

    src = Path(args.file).expanduser().resolve()
    if not src.exists():
        print(f"File not found: {src}", file=sys.stderr)
        return 2
    s = get_settings()
    s.ensure_dirs()
    init_db()
    storage = LocalStorage(s.storage_dir)
    ext = src.suffix.lstrip(".").lower()
    rec_id = new_id()
    dest = storage.original_path(rec_id, ext)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    info = media.probe(dest)
    with session_scope() as db:
        rec = Recording(
            id=rec_id,
            title=args.title or src.stem,
            original_filename=src.name,
            file_ext=ext,
            size_bytes=dest.stat().st_size,
            duration_sec=info.duration_sec,
            sample_rate=info.sample_rate,
            channels=info.channels,
            has_video=info.has_video,
            audio_codec=info.audio_codec,
        )
        db.add(rec)
        db.flush()
        analysis = jobs.enqueue_analysis(db, rec, args.engine or default_engine_id(s))
        analysis.status = "running"
        analysis_id = analysis.id
    print(f"Recording {rec_id}, analysis {analysis_id} – running pipeline…")
    Pipeline(s, storage).run(analysis_id)
    result_path = storage.analysis_file(rec_id, analysis_id, LocalStorage.RESULT_FILE)
    if not result_path.exists():
        print("Pipeline failed; see logs above.", file=sys.stderr)
        return 1
    r = json.loads(result_path.read_text())
    print(
        json.dumps(
            {
                "transcription": {k: r["transcription"].get(k) for k in ("status", "engine", "note_count", "message")},
                "tempo": {k: r["tempo"].get(k) for k in ("bpm", "time_signature", "meter_confidence")},
                "key": r["key"]["label"] if r.get("key") else None,
                "chords": [c["label"] for c in r["chords"]["segments"]][:24],
                "sections": [f"{x['label']} {x['start']:.1f}-{x['end']:.1f}s" for x in r["sections"]],
                "files": r["notation"]["files"],
                "warnings": r["warnings"],
                "output_dir": str(result_path.parent),
            },
            indent=2,
        )
    )
    return 0


def cmd_make_test_audio(args) -> int:
    from app.devtools.synth import gospel_progression, write_wav

    out = Path(args.output)
    write_wav(out, gospel_progression(bpm=args.bpm, bars=args.bars))
    print(f"Wrote synthetic test signal (not a real recording): {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="PianoScribe AI utilities")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor", help="Check the local setup").set_defaults(func=cmd_doctor)
    sub.add_parser("download-models", help="Download model checkpoints").set_defaults(func=cmd_download_models)
    t = sub.add_parser("transcribe", help="Run the full pipeline on a file")
    t.add_argument("file")
    t.add_argument("--title")
    t.add_argument("--engine")
    t.set_defaults(func=cmd_transcribe)
    m = sub.add_parser("make-test-audio", help="Write a synthetic piano WAV with known notes")
    m.add_argument("output", nargs="?", default="test-gospel.wav")
    m.add_argument("--bpm", type=float, default=76.0)
    m.add_argument("--bars", type=int, default=16)
    m.set_defaults(func=cmd_make_test_audio)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
