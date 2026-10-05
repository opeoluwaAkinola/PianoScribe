"""Analysis endpoints: status, full result, downloads, cancel, re-engrave."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.serializers import analysis_out
from app.db import get_db
from app.models import Analysis, AnalysisStatus
from app.schemas import AnalysisOut, RenotateRequest
from app.services import jobs
from app.services.storage import LocalStorage, get_storage

router = APIRouter(prefix="/api/analyses", tags=["analyses"])

FILES = {
    "midi": (LocalStorage.MIDI_FILE, "audio/midi", "mid"),
    "musicxml": (LocalStorage.MUSICXML_FILE, "application/vnd.recordare.musicxml+xml", "musicxml"),
    "pdf": (LocalStorage.PDF_FILE, "application/pdf", "pdf"),
    "json": (LocalStorage.RESULT_FILE, "application/json", "json"),
}


def _get(db: Session, analysis_id: str) -> Analysis:
    a = db.get(Analysis, analysis_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
    return a


def _safe_name(title: str) -> str:
    cleaned = re.sub(r"[^\w\s\-().,'&]+", "", title).strip()
    return cleaned[:120] or "transcription"


@router.get("/{analysis_id}", response_model=AnalysisOut)
def get_analysis(analysis_id: str, db: Session = Depends(get_db), storage: LocalStorage = Depends(get_storage)):
    return analysis_out(_get(db, analysis_id), storage)


@router.get("/{analysis_id}/result")
def get_result(analysis_id: str, db: Session = Depends(get_db), storage: LocalStorage = Depends(get_storage)):
    a = _get(db, analysis_id)
    path = storage.analysis_file(a.recording_id, a.id, LocalStorage.RESULT_FILE)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Result not available yet")
    return FileResponse(path, media_type="application/json")


@router.get("/{analysis_id}/files/{kind}")
def get_file(
    analysis_id: str,
    kind: str,
    download: bool = Query(default=True),
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage),
):
    if kind not in FILES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown file type")
    a = _get(db, analysis_id)
    name, media_type, ext = FILES[kind]
    path = storage.analysis_file(a.recording_id, a.id, name)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No {kind} file for this analysis")
    filename = f"{_safe_name(a.recording.title)}.{ext}" if download else None
    return FileResponse(path, media_type=media_type, filename=filename)


@router.post("/{analysis_id}/cancel", response_model=AnalysisOut)
def cancel(analysis_id: str, db: Session = Depends(get_db), storage: LocalStorage = Depends(get_storage)):
    a = _get(db, analysis_id)
    if a.status not in AnalysisStatus.ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Analysis is already {a.status}")
    jobs.request_cancel(db, a)
    db.commit()
    db.refresh(a)
    return analysis_out(a, storage)


@router.post("/{analysis_id}/renotate", response_model=AnalysisOut, status_code=status.HTTP_201_CREATED)
def renotate(
    analysis_id: str,
    body: RenotateRequest,
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage),
):
    """Re-run tempo/key/chords/notation with overrides, reusing the transcribed notes."""
    src = _get(db, analysis_id)
    if src.status != AnalysisStatus.COMPLETED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only completed analyses can be re-engraved")
    if not storage.analysis_file(src.recording_id, src.id, LocalStorage.RESULT_FILE).exists():
        raise HTTPException(status.HTTP_409_CONFLICT, "Previous result is missing")
    rec = src.recording
    if any(a.status in AnalysisStatus.ACTIVE for a in rec.analyses):
        raise HTTPException(status.HTTP_409_CONFLICT, "An analysis is already queued or running")
    # Overrides accumulate: start from the source's options, apply the new ones.
    options = {k: v for k, v in (src.options or {}).items() if k != "source_analysis_id"}
    options.update({k: v for k, v in body.model_dump().items() if v is not None})
    # The notes always come from the analysis that actually ran the model.
    options["source_analysis_id"] = (src.options or {}).get("source_analysis_id") if src.mode == "renotate" else src.id
    a = jobs.enqueue_analysis(db, rec, src.engine, mode="renotate", options=options)
    db.commit()
    db.refresh(a)
    return analysis_out(a, storage)
