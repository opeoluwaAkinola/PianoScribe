"""SQLite-backed job queue.

Analyses *are* the jobs: the API inserts a row with status "queued" and a
worker process claims it atomically. No Redis needed for a single machine; if
that ever changes, only this module has to be swapped.
"""

from __future__ import annotations

import os
import socket
from datetime import timedelta
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_engine, session_scope
from app.models import Analysis, AnalysisStatus, Recording, WorkerHeartbeat, utcnow
from app.pipeline.progress import initial_stages


def enqueue_analysis(
    db: Session, recording: Recording, engine: str, mode: str = "full", options: dict[str, Any] | None = None
) -> Analysis:
    analysis = Analysis(
        recording_id=recording.id,
        engine=engine,
        mode=mode,
        options=options or {},
        status=AnalysisStatus.QUEUED,
        stages=initial_stages(mode),
        progress=0.0,
    )
    db.add(analysis)
    db.flush()
    return analysis


def claim_next(worker_id: str) -> str | None:
    """Atomically move the oldest queued analysis to running; return its id."""
    with get_engine().begin() as conn:
        row = conn.execute(
            text(
                """
                UPDATE analyses
                   SET status = 'running', worker_id = :w, started_at = :now
                 WHERE id = (SELECT id FROM analyses WHERE status = 'queued'
                              ORDER BY created_at LIMIT 1)
                   AND status = 'queued'
                RETURNING id
                """
            ),
            # Same textual format SQLAlchemy uses for DateTime on SQLite.
            {"w": worker_id, "now": utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")},
        ).first()
    return row[0] if row else None


def request_cancel(db: Session, analysis: Analysis) -> None:
    if analysis.status == AnalysisStatus.QUEUED:
        analysis.status = AnalysisStatus.CANCELLED
        analysis.finished_at = utcnow()
        analysis.stages = [{**s, "status": "cancelled"} if s["status"] == "pending" else s for s in analysis.stages]
    elif analysis.status == AnalysisStatus.RUNNING:
        analysis.cancel_requested = True


def worker_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def heartbeat(worker_id: str, current_analysis_id: str | None) -> None:
    with session_scope() as db:
        hb = db.get(WorkerHeartbeat, worker_id)
        if hb is None:
            hb = WorkerHeartbeat(worker_id=worker_id, pid=os.getpid(), hostname=socket.gethostname())
            db.add(hb)
        hb.last_seen = utcnow()
        hb.current_analysis_id = current_analysis_id


def remove_heartbeat(worker_id: str) -> None:
    with session_scope() as db:
        hb = db.get(WorkerHeartbeat, worker_id)
        if hb is not None:
            db.delete(hb)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _is_dead_local(hb: WorkerHeartbeat) -> bool:
    """A worker on this machine whose process is gone (e.g. killed by a reload)."""
    return hb.hostname == socket.gethostname() and not _pid_alive(hb.pid)


def live_workers(db: Session) -> list[WorkerHeartbeat]:
    cutoff = utcnow() - timedelta(seconds=get_settings().worker_stale_after_sec)
    recent = db.scalars(select(WorkerHeartbeat).where(WorkerHeartbeat.last_seen >= cutoff))
    return [hb for hb in recent if not _is_dead_local(hb)]


def requeue_orphans() -> int:
    """Re-queue analyses left 'running' by workers that died (e.g. Ctrl-C)."""
    with session_scope() as db:
        alive = {w.worker_id for w in live_workers(db)}
        running = list(db.scalars(select(Analysis).where(Analysis.status == AnalysisStatus.RUNNING)))
        n = 0
        for a in running:
            if a.worker_id not in alive:
                a.status = AnalysisStatus.QUEUED
                a.worker_id = None
                a.started_at = None
                a.progress = 0.0
                a.stage = None
                a.stage_message = None
                a.stages = initial_stages(a.mode)
                n += 1
        for hb in db.scalars(select(WorkerHeartbeat)):
            if _is_dead_local(hb):
                db.delete(hb)
        cutoff = utcnow() - timedelta(seconds=get_settings().worker_stale_after_sec * 10)
        db.execute(update(WorkerHeartbeat).where(WorkerHeartbeat.last_seen < cutoff).values(current_analysis_id=None))
        return n
