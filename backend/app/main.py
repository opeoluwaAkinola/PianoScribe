"""FastAPI application entry point.

uvicorn app.main:app --reload --port 8484
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import analyses, recordings, system
from app.config import get_settings
from app.db import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    settings.ensure_dirs()
    init_db()
    worker = None
    if settings.embedded_worker:
        from app.worker.runner import start_embedded

        worker = start_embedded()
    yield
    if worker is not None:
        worker.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="PianoScribe AI", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition", "Content-Range", "Accept-Ranges"],
    )
    app.include_router(system.router)
    app.include_router(recordings.router)
    app.include_router(analyses.router)
    return app


app = create_app()
