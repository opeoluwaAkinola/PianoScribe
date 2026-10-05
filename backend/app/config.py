"""Application settings.

All settings can be overridden with environment variables prefixed with
``PIANOSCRIBE_`` (e.g. ``PIANOSCRIBE_TRANSCRIPTION_ENGINE=basic_pitch``) or
with a ``backend/.env`` file.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PIANOSCRIBE_",
        env_file=BACKEND_DIR / ".env",
        extra="ignore",
    )

    # --- Paths -------------------------------------------------------------
    data_dir: Path = BACKEND_DIR / "data"
    database_url: str | None = None  # defaults to sqlite in data_dir

    # --- API ---------------------------------------------------------------
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3456",
            "http://127.0.0.1:3456",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )
    max_upload_mb: int = 2048
    allowed_extensions: list[str] = Field(default_factory=lambda: ["mp3", "wav", "m4a", "flac", "mp4", "mov"])
    # Run the background worker inside the API process (single-process mode).
    embedded_worker: bool = False

    # --- Transcription -----------------------------------------------------
    # Default transcription engine id (see app/transcription/registry.py).
    transcription_engine: str = "bytedance"
    # Device for torch-based engines: "auto" | "cpu" | "mps" | "cuda".
    torch_device: str = "cpu"
    # Command template for the "external_cli" engine. ``{input}`` is replaced
    # with a 44.1 kHz mono WAV path and ``{output}`` with the MIDI path the
    # command must write, e.g. ``transkun {input} {output}``.
    external_cli_command: str | None = None
    external_cli_timeout_sec: int = 3600

    # --- Tools -------------------------------------------------------------
    ffmpeg_path: str | None = None  # falls back to PATH, then imageio-ffmpeg
    musescore_path: str | None = None  # optional, enables PDF export

    # --- Worker ------------------------------------------------------------
    worker_poll_interval_sec: float = 1.0
    worker_heartbeat_sec: float = 5.0
    worker_stale_after_sec: float = 30.0

    # --- Analysis ----------------------------------------------------------
    analysis_sample_rate: int = 22050
    decode_sample_rate: int = 44100

    @property
    def storage_dir(self) -> Path:
        return self.data_dir / "storage"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.data_dir / 'pianoscribe.db'}"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.storage_dir, self.models_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
