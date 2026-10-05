"""The analysis pipeline.

    Audio ─┬─ decode ─ tempo/beats/meter ─────────────────────────┐
           └─ AI transcription ─ notes ─┬─ key ─ chords ─ sections ┤
                                        └─ MIDI ─ MusicXML ─ PDF ──┘

Each stage is isolated: if transcription isn't available (no model installed)
or fails, the audio-only analyses (tempo, key and chords from the chromagram,
sections) still complete and the result says exactly what's missing. Nothing
is ever invented to fill a gap.
"""

from __future__ import annotations

import logging
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from app.analysis.beatgrid import BeatGrid
from app.analysis.chords import ChordSegment, chords_from_audio, chords_from_notes
from app.analysis.key import KeyAnalysis, analyze_key_from_audio, analyze_key_from_notes, refine_key_with_chords
from app.analysis.sections import Section, detect_sections
from app.analysis.tempo import TempoAnalysis, align_beats_to_onsets, analyze_tempo
from app.analysis.theory import KeyInfo
from app.analysis.types import Note, Pedal, clean_notes, sustained_notes
from app.config import Settings, get_settings
from app.db import session_scope
from app.models import Analysis, AnalysisStatus, Recording, utcnow
from app.notation.midi import write_midi
from app.notation.musicxml import NotationOptions, build_score, write_musicxml
from app.notation.pdf import find_musescore, render_pdf
from app.pipeline.progress import Cancelled, ProgressReporter
from app.services import media
from app.services.storage import LocalStorage
from app.transcription.base import TranscriptionUnavailable
from app.transcription.registry import UnknownEngine, create_engine, get_engine_class

log = logging.getLogger("pianoscribe.pipeline")

RESULT_SCHEMA_VERSION = 1

TIME_SIGNATURES = {"4/4": (4, False), "3/4": (3, False), "2/4": (2, False), "12/8": (4, True), "6/8": (2, True)}


@dataclass
class Ctx:
    analysis_id: str
    recording_id: str
    title: str
    file_ext: str
    engine_id: str
    mode: str
    options: dict[str, Any]
    out_dir: Path
    duration: float = 0.0
    y: np.ndarray | None = None
    sr: int = 22050
    tempo: TempoAnalysis | None = None
    grid: BeatGrid | None = None
    notes: list[Note] = field(default_factory=list)
    pedals: list[Pedal] = field(default_factory=list)
    transcription: dict[str, Any] = field(default_factory=dict)
    key: KeyAnalysis | None = None
    chords: list[ChordSegment] = field(default_factory=list)
    chord_source: str | None = None
    sections: list[Section] = field(default_factory=list)
    notation: dict[str, Any] = field(default_factory=dict)
    files: dict[str, bool] = field(default_factory=lambda: {"midi": False, "musicxml": False, "pdf": False})
    warnings: list[str] = field(default_factory=list)
    previous: dict[str, Any] | None = None


def _short_error(exc: BaseException) -> str:
    msg = str(exc).strip() or exc.__class__.__name__
    return msg if len(msg) < 400 else msg[:400] + "…"


class Pipeline:
    def __init__(self, settings: Settings | None = None, storage: LocalStorage | None = None) -> None:
        self.settings = settings or get_settings()
        self.storage = storage or LocalStorage(self.settings.storage_dir)

    # --- Entry point --------------------------------------------------------
    def run(self, analysis_id: str) -> None:
        with session_scope() as db:
            a = db.get(Analysis, analysis_id)
            if a is None:
                return
            rec = a.recording
            ctx = Ctx(
                analysis_id=a.id,
                recording_id=rec.id,
                title=rec.title,
                file_ext=rec.file_ext,
                engine_id=a.engine,
                mode=a.mode,
                options=dict(a.options or {}),
                out_dir=self.storage.analysis_dir(rec.id, a.id),
                duration=rec.duration_sec or 0.0,
            )
        reporter = ProgressReporter(analysis_id, ctx.mode)
        ctx.out_dir.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        try:
            if ctx.mode == "renotate":
                self._load_previous(ctx)
            else:
                self._decode(ctx, reporter)
            self._load_audio(ctx)
            self._tempo(ctx, reporter)
            if ctx.mode != "renotate":
                self._transcribe(ctx, reporter)
            self._build_grid(ctx)
            self._key(ctx, reporter)
            self._chords(ctx, reporter)
            self._sections(ctx, reporter)
            self._midi(ctx, reporter)
            self._musicxml(ctx, reporter)
            self._pdf(ctx, reporter)
            self._write_result(ctx)
            self._finish(ctx, AnalysisStatus.COMPLETED, reporter, None)
            log.info("analysis %s completed in %.1fs", analysis_id, time.monotonic() - started)
        except Cancelled as exc:
            self._finish(ctx, AnalysisStatus.CANCELLED, reporter, str(exc))
        except Exception as exc:  # noqa: BLE001 - report any failure to the user
            log.error("analysis %s failed:\n%s", analysis_id, traceback.format_exc())
            self._finish(ctx, AnalysisStatus.FAILED, reporter, _short_error(exc))

    # --- Stages -------------------------------------------------------------
    def _decode(self, ctx: Ctx, rep: ProgressReporter) -> None:
        rep.start("decode", "Decoding with ffmpeg")
        original = self.storage.original_path(ctx.recording_id, ctx.file_ext)
        wav = self.storage.audio_path(ctx.recording_id)
        playback = self.storage.playback_path(ctx.recording_id)
        if not wav.exists() or wav.stat().st_mtime < original.stat().st_mtime:
            media.decode_to_wav(original, wav, self.settings.decode_sample_rate)
        rep.update(0.6, "Preparing playback audio")
        if not playback.exists():
            try:
                media.make_playback_audio(original, playback)
            except media.MediaError as exc:
                ctx.warnings.append(f"Could not create playback audio: {exc}")
        info = media.probe(wav)
        ctx.duration = info.duration_sec or ctx.duration
        with session_scope() as db:
            rec = db.get(Recording, ctx.recording_id)
            if rec is not None and info.duration_sec:
                rec.duration_sec = info.duration_sec
        rep.finish("decode", message=f"{ctx.duration:.1f} s of audio")

    def _load_audio(self, ctx: Ctx) -> None:
        import librosa

        wav = self.storage.audio_path(ctx.recording_id)
        if not wav.exists():
            raise RuntimeError("Decoded audio is missing; run a full analysis first.")
        ctx.sr = self.settings.analysis_sample_rate
        y, _ = librosa.load(str(wav), sr=ctx.sr, mono=True)
        if y.size == 0 or float(np.max(np.abs(y))) < 1e-4:
            raise RuntimeError("The recording appears to be silent.")
        ctx.y = y
        ctx.duration = len(y) / ctx.sr

    def _tempo(self, ctx: Ctx, rep: ProgressReporter) -> None:
        rep.start("tempo", "Tracking beats")
        bpm_hint = ctx.options.get("bpm")
        ts = ctx.options.get("time_signature")
        meter = TIME_SIGNATURES.get(ts) if ts else None
        try:
            ctx.tempo = analyze_tempo(
                ctx.y, ctx.sr, bpm_hint=float(bpm_hint) if bpm_hint else None, meter_override=meter
            )
            shift = int(ctx.options.get("downbeat_shift") or 0)
            if shift and not ctx.tempo.fallback:
                ctx.tempo.first_downbeat_index = (ctx.tempo.first_downbeat_index + shift) % ctx.tempo.beats_per_bar
            msg = f"{ctx.tempo.bpm:.0f} BPM · {ctx.tempo.time_signature}"
            if ctx.tempo.fallback:
                ctx.warnings.append("No steady beat was found; bar lines use a constant 120 BPM grid.")
                msg = "No steady beat found"
            rep.finish("tempo", message=msg)
        except Exception as exc:
            log.exception("tempo failed")
            ctx.warnings.append(f"Tempo detection failed: {_short_error(exc)}")
            ctx.tempo = TempoAnalysis(120.0, np.asarray([]), 4, False, 0, 0.0, 1.0, 1.0, np.asarray([]), True)
            rep.finish("tempo", status="failed", message=_short_error(exc))

    def _transcribe(self, ctx: Ctx, rep: ProgressReporter) -> None:
        rep.start("transcription", "Loading engine")
        t0 = time.monotonic()
        try:
            cls = get_engine_class(ctx.engine_id)
        except UnknownEngine as exc:
            ctx.transcription = {"status": "failed", "engine": ctx.engine_id, "message": str(exc)}
            rep.finish("transcription", status="failed", message=str(exc))
            return
        base = {"engine": cls.id, "engine_label": cls.label}
        avail = cls.availability(self.settings)
        if not avail.available:
            msg = avail.reason or "Engine unavailable"
            ctx.transcription = {**base, "status": "unavailable", "message": msg, "install_hint": avail.install_hint}
            ctx.warnings.append(
                f"AI transcription skipped – {cls.label} is not available: {msg}. "
                "Notes, MIDI and sheet music need a transcription engine."
            )
            rep.finish("transcription", status="unavailable", message=msg)
            return
        try:
            engine = create_engine(ctx.engine_id, self.settings)
            out = engine.transcribe(self.storage.audio_path(ctx.recording_id), rep.update)
            ctx.notes = clean_notes(out.notes)
            ctx.pedals = [p for p in out.pedals if p.end > p.start]
            ctx.transcription = {
                **base,
                "status": "completed",
                "model": out.model,
                "message": None,
                "note_count": len(ctx.notes),
                "pedal_count": len(ctx.pedals),
                "elapsed_sec": round(time.monotonic() - t0, 2),
                "details": out.details,
            }
            if not ctx.notes:
                ctx.warnings.append("The transcription engine ran but detected no notes.")
            rep.finish("transcription", message=f"{len(ctx.notes)} notes in {time.monotonic() - t0:.0f} s")
        except Cancelled:
            raise
        except TranscriptionUnavailable as exc:
            ctx.transcription = {**base, "status": "unavailable", "message": _short_error(exc)}
            ctx.warnings.append(f"AI transcription unavailable: {_short_error(exc)}")
            rep.finish("transcription", status="unavailable", message=_short_error(exc))
        except Exception as exc:
            log.exception("transcription failed")
            ctx.transcription = {**base, "status": "failed", "message": _short_error(exc)}
            ctx.warnings.append(f"AI transcription failed: {_short_error(exc)}")
            rep.finish("transcription", status="failed", message=_short_error(exc))

    def _build_grid(self, ctx: Ctx) -> None:
        assert ctx.tempo is not None
        if ctx.notes:
            onsets = np.array([n.start for n in ctx.notes])
            if not ctx.tempo.fallback:
                ctx.tempo.beat_times = align_beats_to_onsets(ctx.tempo.beat_times, onsets)
            solid = [n.start for n in ctx.notes if n.velocity >= 25 and n.duration >= 0.04]
            origin = solid[0] if solid else ctx.notes[0].start
        else:
            import librosa

            onsets = librosa.onset.onset_detect(y=ctx.y, sr=ctx.sr, units="time")
            origin = float(onsets[0]) if len(onsets) else 0.0
        ctx.grid = ctx.tempo.grid(ctx.duration, origin_time=max(0.0, origin))

    def _key(self, ctx: Ctx, rep: ProgressReporter) -> None:
        rep.start("key")
        override = ctx.options.get("key")
        try:
            if override:
                k = KeyInfo.parse(override)
                ctx.key = KeyAnalysis(k, 1.0, "override", [], np.zeros(12))
            elif ctx.notes:
                ctx.key = analyze_key_from_notes(ctx.notes)
            else:
                ctx.key = analyze_key_from_audio(ctx.y, ctx.sr)
            rep.finish("key", message=f"{ctx.key.key.label} (from {ctx.key.source})")
        except Exception as exc:
            log.exception("key failed")
            ctx.key = KeyAnalysis(KeyInfo(0, "major"), 0.0, "fallback", [], np.zeros(12))
            ctx.warnings.append(f"Key detection failed: {_short_error(exc)}")
            rep.finish("key", status="failed", message=_short_error(exc))

    def _chords(self, ctx: Ctx, rep: ProgressReporter) -> None:
        rep.start("chords")
        try:
            if ctx.notes:
                heard = sustained_notes(ctx.notes, ctx.pedals)
                ctx.chords = chords_from_notes(heard, ctx.grid, ctx.duration)
                ctx.chord_source = "notes"
            else:
                rep.update(0.1, "Analysing chromagram")
                ctx.chords = chords_from_audio(ctx.y, ctx.sr, ctx.grid, ctx.duration)
                ctx.chord_source = "audio"
            n = sum(1 for c in ctx.chords if c.root_pc is not None)
            msg = f"{n} chord changes (from {ctx.chord_source})"
            if ctx.key is not None:
                ctx.key = refine_key_with_chords(
                    ctx.key,
                    [(c.root_pc, c.quality.suffix, c.end - c.start) for c in ctx.chords if c.root_pc is not None],
                )
                if ctx.key.refined_by_chords:
                    msg += f"; key revised to {ctx.key.key.label} from the harmony"
            rep.finish("chords", message=msg)
        except Exception as exc:
            log.exception("chords failed")
            ctx.warnings.append(f"Chord detection failed: {_short_error(exc)}")
            rep.finish("chords", status="failed", message=_short_error(exc))

    def _sections(self, ctx: Ctx, rep: ProgressReporter) -> None:
        rep.start("sections")
        try:
            ctx.sections = detect_sections(ctx.y, ctx.sr, ctx.grid, ctx.duration)
            rep.finish("sections", message=f"{len(ctx.sections)} sections")
        except Exception as exc:
            log.exception("sections failed")
            ctx.warnings.append(f"Section detection failed: {_short_error(exc)}")
            rep.finish("sections", status="failed", message=_short_error(exc))

    def _midi(self, ctx: Ctx, rep: ProgressReporter) -> None:
        if not ctx.notes:
            rep.skip("midi", "Needs a transcription", status="unavailable")
            return
        rep.start("midi")
        try:
            write_midi(
                ctx.out_dir / LocalStorage.MIDI_FILE,
                ctx.notes,
                ctx.pedals,
                ctx.grid,
                ctx.key.key if ctx.key else None,
                ctx.title,
            )
            ctx.files["midi"] = True
            rep.finish("midi")
        except Exception as exc:
            log.exception("midi failed")
            ctx.warnings.append(f"MIDI export failed: {_short_error(exc)}")
            rep.finish("midi", status="failed", message=_short_error(exc))

    def _musicxml(self, ctx: Ctx, rep: ProgressReporter) -> None:
        if not ctx.notes:
            rep.skip("musicxml", "Needs a transcription", status="unavailable")
            return
        rep.start("musicxml", "Quantising and engraving")
        try:
            opts = NotationOptions(
                hand_split=int(ctx.options.get("hand_split") or 60),
                subdivisions=int(ctx.options["subdivisions"]) if ctx.options.get("subdivisions") else None,
                chord_symbols=bool(ctx.options.get("chord_symbols", True)),
            )
            score, info = build_score(ctx.notes, ctx.grid, ctx.key.key, ctx.tempo.bpm, ctx.chords, ctx.title, opts)
            rep.update(0.7, "Writing MusicXML")
            write_musicxml(ctx.out_dir / LocalStorage.MUSICXML_FILE, score)
            ctx.files["musicxml"] = True
            ctx.notation = {
                "measures": info.measures,
                "subdivisions": info.subdivisions,
                "hand_split": info.hand_split,
                "chord_symbols": opts.chord_symbols,
            }
            rep.finish("musicxml", message=f"{info.measures} bars")
        except Exception as exc:
            log.exception("musicxml failed")
            ctx.warnings.append(f"Sheet music engraving failed: {_short_error(exc)}")
            rep.finish("musicxml", status="failed", message=_short_error(exc))

    def _pdf(self, ctx: Ctx, rep: ProgressReporter) -> None:
        if not ctx.files["musicxml"]:
            rep.skip("pdf", "Needs sheet music", status="unavailable")
            return
        if not find_musescore():
            rep.skip("pdf", "MuseScore not installed – use Print in the sheet-music view")
            return
        rep.start("pdf", "Rendering with MuseScore")
        try:
            render_pdf(ctx.out_dir / LocalStorage.MUSICXML_FILE, ctx.out_dir / LocalStorage.PDF_FILE)
            ctx.files["pdf"] = True
            rep.finish("pdf")
        except Exception as exc:
            ctx.warnings.append(f"PDF rendering failed: {_short_error(exc)}")
            rep.finish("pdf", status="failed", message=_short_error(exc))

    # --- Renotate support ----------------------------------------------------
    def _load_previous(self, ctx: Ctx) -> None:
        source_id = ctx.options.get("source_analysis_id") or ctx.analysis_id
        path = self.storage.analysis_file(ctx.recording_id, source_id, LocalStorage.RESULT_FILE)
        if not path.exists():
            raise RuntimeError("No previous result to re-engrave; run a full analysis.")
        prev = self.storage.read_json(path)
        ctx.previous = prev
        ctx.notes = [Note.from_dict(d) for d in prev.get("notes", [])]
        ctx.pedals = [Pedal.from_dict(d) for d in prev.get("pedals", [])]
        ctx.transcription = prev.get("transcription", {})

    # --- Output -------------------------------------------------------------
    def _write_result(self, ctx: Ctx) -> None:
        key = ctx.key.key if ctx.key else KeyInfo(0, "major")
        grid = ctx.grid
        tempo = ctx.tempo.to_dict() if ctx.tempo else {}
        if grid is not None:
            tempo["grid"] = grid.to_dict()
            tempo["beats"] = [round(b, 4) for b in grid.all_beat_times()]
            tempo["downbeats"] = [round(b, 4) for b in grid.downbeat_times()]
            tempo["start_position"] = round(grid.start_position, 4)
            tempo["bar_count"] = grid.bar_count()
            tempo["time_signature"] = grid.time_signature
        result = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "analysis_id": ctx.analysis_id,
            "recording_id": ctx.recording_id,
            "generated_at": utcnow().isoformat(),
            "mode": ctx.mode,
            "duration": round(ctx.duration, 3),
            "transcription": ctx.transcription,
            "notes": [n.to_dict() for n in ctx.notes],
            "pedals": [p.to_dict() for p in ctx.pedals],
            "tempo": tempo,
            "key": ctx.key.to_dict() if ctx.key else None,
            "chords": {
                "source": ctx.chord_source,
                "segments": [c.to_dict(key) for c in ctx.chords],
            },
            "sections": [s.to_dict() for s in ctx.sections],
            "notation": {**ctx.notation, "files": ctx.files},
            "options": ctx.options,
            "warnings": ctx.warnings,
        }
        self.storage.write_json(ctx.out_dir / LocalStorage.RESULT_FILE, result)

    def _finish(self, ctx: Ctx, status: str, rep: ProgressReporter, error: str | None) -> None:
        with session_scope() as db:
            a = db.get(Analysis, ctx.analysis_id)
            if a is None:
                return
            a.status = status
            a.finished_at = utcnow()
            a.error = error
            a.stages = [
                {**s, "status": "cancelled" if status == AnalysisStatus.CANCELLED else "failed"}
                if s["status"] in ("running", "pending") and status != AnalysisStatus.COMPLETED
                else s
                for s in rep.stages
            ]
            a.stage = None
            a.stage_message = None
            a.warnings = ctx.warnings
            if status == AnalysisStatus.COMPLETED:
                a.progress = 1.0
                a.transcription_status = ctx.transcription.get("status")
                a.transcription_message = ctx.transcription.get("message")
                a.bpm = round(ctx.tempo.bpm, 2) if ctx.tempo else None
                a.key = ctx.key.key.label if ctx.key else None
                a.time_signature = ctx.grid.time_signature if ctx.grid else None
                a.note_count = len(ctx.notes)
                a.chord_count = sum(1 for c in ctx.chords if c.root_pc is not None)
                a.section_count = len(ctx.sections)
