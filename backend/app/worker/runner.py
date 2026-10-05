"""Background worker: polls the queue and runs analyses one at a time.

Run it with ``python -m app.worker`` (``./dev.sh`` does this for you), or set
``PIANOSCRIBE_EMBEDDED_WORKER=true`` to run it inside the API process.
"""

from __future__ import annotations

import logging
import signal
import threading
import time

from app.config import get_settings
from app.db import init_db
from app.pipeline.runner import Pipeline
from app.services import jobs

log = logging.getLogger("pianoscribe.worker")


class Worker:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.worker_id = jobs.worker_identity()
        self.current: str | None = None
        self._stop = threading.Event()
        self._pipeline = Pipeline(self.settings)

    def stop(self) -> None:
        self._stop.set()

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self.settings.worker_heartbeat_sec):
            try:
                jobs.heartbeat(self.worker_id, self.current)
            except Exception:  # pragma: no cover - transient DB lock etc.
                log.exception("heartbeat failed")

    def run(self, once: bool = False) -> None:
        init_db()
        jobs.heartbeat(self.worker_id, None)
        requeued = jobs.requeue_orphans()
        if requeued:
            log.info("re-queued %d interrupted analyses", requeued)
        hb = threading.Thread(target=self._heartbeat_loop, name="heartbeat", daemon=True)
        hb.start()
        log.info("worker %s ready (engine default: %s)", self.worker_id, self.settings.transcription_engine)
        try:
            while not self._stop.is_set():
                analysis_id = jobs.claim_next(self.worker_id)
                if analysis_id is None:
                    if once:
                        break
                    self._stop.wait(self.settings.worker_poll_interval_sec)
                    continue
                self.current = analysis_id
                jobs.heartbeat(self.worker_id, analysis_id)
                log.info("running analysis %s", analysis_id)
                try:
                    self._pipeline.run(analysis_id)
                finally:
                    self.current = None
                    jobs.heartbeat(self.worker_id, None)
        finally:
            self._stop.set()
            jobs.remove_heartbeat(self.worker_id)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    worker = Worker()

    def _shutdown(signum, _frame):
        log.info("shutting down (signal %s)…", signum)
        worker.stop()
        # A second Ctrl-C exits immediately; the job is re-queued on next start.
        signal.signal(signal.SIGINT, signal.SIG_DFL)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    worker.run()


def start_embedded() -> Worker:
    worker = Worker()
    threading.Thread(target=worker.run, name="embedded-worker", daemon=True).start()
    time.sleep(0)  # let the thread start
    return worker
