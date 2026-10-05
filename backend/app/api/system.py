"""Health and system-status endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import __version__
from app.config import Settings, get_settings
from app.db import get_db
from app.models import Analysis
from app.notation.pdf import find_musescore
from app.schemas import EngineOut, SystemStatus, ToolStatus, WorkerOut
from app.services import jobs, media
from app.transcription.registry import default_engine_id, describe_engines

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/system", response_model=SystemStatus)
def system_status(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    ffmpeg = media.find_ffmpeg()
    musescore = find_musescore()
    workers = jobs.live_workers(db)
    counts = dict(db.execute(select(Analysis.status, func.count()).group_by(Analysis.status)).all())
    return SystemStatus(
        version=__version__,
        ffmpeg=ToolStatus(available=bool(ffmpeg), path=ffmpeg, version=media.ffmpeg_version() if ffmpeg else None),
        musescore=ToolStatus(available=bool(musescore), path=musescore),
        engines=[EngineOut(**e) for e in describe_engines(settings)],
        default_engine=default_engine_id(settings),
        workers=[WorkerOut.model_validate(w, from_attributes=True) for w in workers],
        worker_online=bool(workers),
        queue={"queued": counts.get("queued", 0), "running": counts.get("running", 0)},
        data_dir=str(settings.data_dir),
        torch_device=settings.torch_device,
        allowed_extensions=settings.allowed_extensions,
        max_upload_mb=settings.max_upload_mb,
    )
