"""Recording endpoints: upload, list, rename, delete, audio, re-analyse."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.serializers import analysis_out, recording_detail, recording_out
from app.config import Settings, get_settings
from app.db import get_db
from app.models import Analysis, AnalysisStatus, Recording, new_id
from app.schemas import AnalysisOut, AnalyzeRequest, RecordingDetail, RecordingOut, RecordingUpdate
from app.services import jobs, media
from app.services.storage import LocalStorage, UploadTooLarge, get_storage
from app.transcription.registry import ENGINES, default_engine_id

router = APIRouter(prefix="/api/recordings", tags=["recordings"])

BROWSER_PLAYABLE = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "m4a": "audio/mp4",
    "flac": "audio/flac",
    "mp4": "video/mp4",
}


def _get_recording(db: Session, recording_id: str) -> Recording:
    rec = db.get(Recording, recording_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recording not found")
    return rec


def _resolve_engine(engine: str | None, settings: Settings) -> str:
    engine = engine or default_engine_id(settings)
    if engine not in ENGINES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown transcription engine: {engine}")
    return engine


@router.get("", response_model=list[RecordingOut])
def list_recordings(db: Session = Depends(get_db), storage: LocalStorage = Depends(get_storage)):
    recs = db.scalars(select(Recording).order_by(Recording.created_at.desc())).all()
    return [recording_out(r, storage) for r in recs]


@router.post("", response_model=RecordingDetail, status_code=status.HTTP_201_CREATED)
def upload_recording(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    engine: str | None = Form(default=None),
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    filename = Path(file.filename or "recording").name
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in settings.allowed_extensions:
        allowed = ", ".join(e.upper() for e in settings.allowed_extensions)
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"Unsupported file type .{ext}. Allowed: {allowed}")
    engine_id = _resolve_engine(engine, settings)

    rec_id = new_id()
    try:
        path, size = storage.save_upload(rec_id, ext, file.file, settings.max_upload_bytes)
    except UploadTooLarge as exc:
        storage.delete_recording(rec_id)
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(exc)) from exc

    try:
        info = media.probe(path)
    except media.MediaError as exc:
        storage.delete_recording(rec_id)
        raise HTTPException(422, str(exc)) from exc
    if not info.has_audio:
        storage.delete_recording(rec_id)
        raise HTTPException(422, "No audio track found in this file.")

    clean_title = (title or "").strip() or filename.rsplit(".", 1)[0]
    rec = Recording(
        id=rec_id,
        title=clean_title[:300],
        original_filename=filename[:500],
        file_ext=ext,
        content_type=file.content_type,
        size_bytes=size,
        duration_sec=info.duration_sec,
        sample_rate=info.sample_rate,
        channels=info.channels,
        has_video=info.has_video,
        audio_codec=info.audio_codec,
    )
    db.add(rec)
    db.flush()
    jobs.enqueue_analysis(db, rec, engine_id)
    db.commit()
    db.refresh(rec)
    return recording_detail(rec, storage)


@router.get("/{recording_id}", response_model=RecordingDetail)
def get_recording(recording_id: str, db: Session = Depends(get_db), storage: LocalStorage = Depends(get_storage)):
    return recording_detail(_get_recording(db, recording_id), storage)


@router.patch("/{recording_id}", response_model=RecordingDetail)
def update_recording(
    recording_id: str,
    body: RecordingUpdate,
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage),
):
    rec = _get_recording(db, recording_id)
    rec.title = body.title.strip()
    db.commit()
    db.refresh(rec)
    return recording_detail(rec, storage)


@router.delete("/{recording_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recording(recording_id: str, db: Session = Depends(get_db), storage: LocalStorage = Depends(get_storage)):
    rec = _get_recording(db, recording_id)
    for a in rec.analyses:
        if a.status in AnalysisStatus.ACTIVE:
            jobs.request_cancel(db, a)
    db.delete(rec)
    db.commit()
    storage.delete_recording(recording_id)


@router.get("/{recording_id}/audio")
def get_audio(recording_id: str, db: Session = Depends(get_db), storage: LocalStorage = Depends(get_storage)):
    rec = _get_recording(db, recording_id)
    playback = storage.playback_path(rec.id)
    if playback.exists():
        return FileResponse(playback, media_type="audio/mp4")
    original = storage.original_path(rec.id, rec.file_ext)
    if rec.file_ext in BROWSER_PLAYABLE and original.exists():
        return FileResponse(original, media_type=BROWSER_PLAYABLE[rec.file_ext])
    raise HTTPException(status.HTTP_409_CONFLICT, "Playback audio is still being prepared")


@router.get("/{recording_id}/original")
def download_original(recording_id: str, db: Session = Depends(get_db), storage: LocalStorage = Depends(get_storage)):
    rec = _get_recording(db, recording_id)
    path = storage.original_path(rec.id, rec.file_ext)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Original file missing")
    return FileResponse(path, filename=rec.original_filename)


@router.post("/{recording_id}/analyses", response_model=AnalysisOut, status_code=status.HTTP_201_CREATED)
def reanalyze(
    recording_id: str,
    body: AnalyzeRequest,
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    rec = _get_recording(db, recording_id)
    if any(a.status in AnalysisStatus.ACTIVE for a in rec.analyses):
        raise HTTPException(status.HTTP_409_CONFLICT, "An analysis is already queued or running")
    analysis: Analysis = jobs.enqueue_analysis(db, rec, _resolve_engine(body.engine, settings))
    db.commit()
    db.refresh(analysis)
    return analysis_out(analysis, storage)
