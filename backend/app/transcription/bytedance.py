"""ByteDance "High-resolution Piano Transcription with Pedals" (Kong et al., 2021).

A CRNN trained on the MAESTRO dataset of real piano performances. It predicts
note onsets, offsets and velocities at 100 frames/s with sub-frame regression,
plus sustain-pedal events. Reported onset F1 ≈ 96.7 % on MAESTRO.

Package: https://github.com/qiuqiangkong/piano_transcription_inference
Install: ``pip install -r requirements-ml.txt`` (torch + piano_transcription_inference)

The ~165 MB checkpoint is downloaded on first use into ``data/models/``
(or ahead of time with ``python -m app.cli download-models``).
"""

from __future__ import annotations

import importlib.util
import ssl
import threading
import urllib.request
from pathlib import Path

import numpy as np

from app.analysis.types import Note, Pedal
from app.config import Settings
from app.transcription.base import (
    EngineAvailability,
    ProgressFn,
    TranscriptionEngine,
    TranscriptionOutput,
    TranscriptionUnavailable,
)

CHECKPOINT_NAME = "note_F1=0.9677_pedal_F1=0.9186.pth"
CHECKPOINT_URL = "https://zenodo.org/record/4034264/files/CRNN_note_F1%3D0.9677_pedal_F1%3D0.9186.pth?download=1"
CHECKPOINT_MIN_BYTES = 160_000_000
SAMPLE_RATE = 16000
BATCH_SIZE = 1  # batching measured slower on CPU (M2), so keep 1

_model_cache: dict[str, object] = {}
_model_lock = threading.Lock()


def checkpoint_path(settings: Settings) -> Path:
    return settings.models_dir / "bytedance" / CHECKPOINT_NAME


def checkpoint_ready(settings: Settings) -> bool:
    p = checkpoint_path(settings)
    if p.exists() and p.stat().st_size >= CHECKPOINT_MIN_BYTES:
        return True
    # Reuse a checkpoint downloaded by the package's own CLI, if present.
    legacy = Path.home() / "piano_transcription_inference_data" / CHECKPOINT_NAME
    return legacy.exists() and legacy.stat().st_size >= CHECKPOINT_MIN_BYTES


def _ssl_context() -> ssl.SSLContext:
    # python.org builds on macOS ship without system CA certificates; certifi's
    # bundle keeps verification on without requiring "Install Certificates".
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:  # pragma: no cover
        return ssl.create_default_context()


def download_checkpoint(settings: Settings, progress: ProgressFn | None = None) -> Path:
    dest = checkpoint_path(settings)
    if dest.exists() and dest.stat().st_size >= CHECKPOINT_MIN_BYTES:
        return dest
    legacy = Path.home() / "piano_transcription_inference_data" / CHECKPOINT_NAME
    if legacy.exists() and legacy.stat().st_size >= CHECKPOINT_MIN_BYTES:
        return legacy
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    req = urllib.request.Request(CHECKPOINT_URL, headers={"User-Agent": "PianoScribe/1.0"})
    with urllib.request.urlopen(req, timeout=60, context=_ssl_context()) as resp, open(tmp, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0) or 172_000_000
        done = 0
        while chunk := resp.read(1 << 20):
            out.write(chunk)
            done += len(chunk)
            if progress:
                progress(min(done / total, 1.0), f"Downloading model {done / 1e6:.0f}/{total / 1e6:.0f} MB")
    if tmp.stat().st_size < CHECKPOINT_MIN_BYTES:
        tmp.unlink(missing_ok=True)
        raise TranscriptionUnavailable("Model download was incomplete; please retry.")
    tmp.replace(dest)
    return dest


def _resolve_device(name: str):
    import torch

    if name == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        return torch.device("cpu")
    if name == "mps" and not torch.backends.mps.is_available():
        return torch.device("cpu")
    if name == "cuda" and not torch.cuda.is_available():
        return torch.device("cpu")
    return torch.device(name)


class ByteDancePianoEngine(TranscriptionEngine):
    id = "bytedance"
    label = "ByteDance Piano Transcription"
    description = (
        "High-resolution piano transcription with pedal detection (Kong et al. 2021), "
        "trained on the MAESTRO concert-piano dataset. Best accuracy for solo piano."
    )
    piano_specific = True

    @classmethod
    def availability(cls, settings: Settings) -> EngineAvailability:
        missing = [m for m in ("torch", "piano_transcription_inference") if importlib.util.find_spec(m) is None]
        if missing:
            return EngineAvailability(
                False,
                reason=f"Python package(s) not installed: {', '.join(missing)}",
                install_hint="cd backend && .venv/bin/python -m pip install -r requirements-ml.txt",
            )
        ready = checkpoint_ready(settings)
        return EngineAvailability(
            True,
            reason=None if ready else "Model checkpoint (~165 MB) will be downloaded on first use.",
            install_hint=None if ready else "Pre-download with: python -m app.cli download-models",
            details={"checkpoint_ready": ready, "device": settings.torch_device},
        )

    def _load_model(self, progress: ProgressFn):
        import torch
        from piano_transcription_inference import config as ptconfig
        from piano_transcription_inference.models import Note_pedal

        device = _resolve_device(self.settings.torch_device)
        key = str(device)
        with _model_lock:
            if key in _model_cache:
                return _model_cache[key], device, ptconfig
            ckpt = download_checkpoint(self.settings, lambda f, m: progress(0.05 * f, m))
            progress(0.06, "Loading model")
            model = Note_pedal(frames_per_second=ptconfig.frames_per_second, classes_num=ptconfig.classes_num)
            try:
                state = torch.load(str(ckpt), map_location=device, weights_only=True)
            except Exception:
                # Older checkpoints may pickle extra metadata. This file comes
                # from the official Zenodo record, so a full load is acceptable.
                state = torch.load(str(ckpt), map_location=device, weights_only=False)
            model.load_state_dict(state["model"], strict=False)
            model.to(device)
            model.eval()
            _model_cache[key] = model
            return model, device, ptconfig

    def transcribe(self, audio_path: Path, progress: ProgressFn) -> TranscriptionOutput:
        if not self.availability(self.settings).available:
            raise TranscriptionUnavailable(self.availability(self.settings).reason or "Unavailable")
        import librosa
        import torch
        from piano_transcription_inference.utilities import RegressionPostProcessor

        model, device, cfg = self._load_model(progress)

        progress(0.08, "Preparing audio")
        audio, _ = librosa.load(str(audio_path), sr=SAMPLE_RATE, mono=True)
        audio_len = len(audio)
        segment = SAMPLE_RATE * 10
        pad = int(np.ceil(audio_len / segment)) * segment - audio_len
        padded = np.concatenate([audio, np.zeros(pad, dtype=audio.dtype)])

        # 10 s segments with 50 % overlap (same scheme as the reference code).
        starts = list(range(0, len(padded) - segment + 1, segment // 2))
        outputs: dict[str, list[np.ndarray]] = {}
        batch_size = BATCH_SIZE
        with torch.no_grad():
            for i in range(0, len(starts), batch_size):
                chunk = starts[i : i + batch_size]
                frames = np.stack([padded[s : s + segment] for s in chunk]).astype(np.float32)
                out = model(torch.from_numpy(frames).to(device))
                for k, v in out.items():
                    outputs.setdefault(k, []).append(v.detach().cpu().numpy())
                done = min(i + batch_size, len(starts))
                progress(0.1 + 0.85 * done / len(starts), f"Transcribing segment {done}/{len(starts)}")

        output_dict = {k: self._deframe(np.concatenate(v, axis=0))[:audio_len] for k, v in outputs.items()}
        # Frames, not samples, after deframing; trim to the audio's frame count.
        n_frames = int(np.ceil(audio_len / SAMPLE_RATE * cfg.frames_per_second)) + 1
        output_dict = {k: v[:n_frames] for k, v in output_dict.items()}

        progress(0.96, "Decoding notes")
        post = RegressionPostProcessor(
            cfg.frames_per_second,
            classes_num=cfg.classes_num,
            onset_threshold=0.3,
            offset_threshold=0.3,
            frame_threshold=0.1,
            pedal_offset_threshold=0.2,
        )
        note_events, pedal_events = post.output_dict_to_midi_events(output_dict)
        notes = [
            Note(int(e["midi_note"]), float(e["onset_time"]), float(e["offset_time"]), int(e["velocity"]))
            for e in note_events
        ]
        pedals = [Pedal(float(e["onset_time"]), float(e["offset_time"])) for e in (pedal_events or [])]
        progress(1.0, None)
        return TranscriptionOutput(
            notes=notes,
            pedals=pedals,
            model="CRNN note_F1=0.9677 pedal_F1=0.9186 (MAESTRO)",
            details={"device": str(device), "segments": len(starts)},
        )

    @staticmethod
    def _deframe(x: np.ndarray) -> np.ndarray:
        """Stitch overlapping segment predictions (mirrors the reference code)."""
        if x.shape[0] == 1:
            return x[0]
        x = x[:, :-1, :]
        n, seg_frames, _ = x.shape
        q = seg_frames // 4
        parts = [x[0, : 3 * q]]
        for i in range(1, n - 1):
            parts.append(x[i, q : 3 * q])
        parts.append(x[-1, q:])
        return np.concatenate(parts, axis=0)
