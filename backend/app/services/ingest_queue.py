from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import logging
from threading import Lock
from typing import Any, Callable

from app.core.config import settings

logger = logging.getLogger(__name__)


class IngestQueue:
    def __init__(self, max_workers: int):
        self.max_workers = max(1, int(max_workers))
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="ingest")
        self._lock = Lock()
        self._running = 0
        self._queued = 0

    def submit(self, func: Callable[..., Any], *args, **kwargs) -> Future:
        with self._lock:
            self._queued += 1

        def _runner():
            with self._lock:
                self._queued = max(0, self._queued - 1)
                self._running += 1
            try:
                return func(*args, **kwargs)
            finally:
                with self._lock:
                    self._running = max(0, self._running - 1)

        return self._executor.submit(_runner)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "running_workers": int(self._running),
                "queued_jobs": int(self._queued),
                "max_workers": int(self.max_workers),
            }

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)


_queue_instance: IngestQueue | None = None


def get_ingest_queue() -> IngestQueue:
    global _queue_instance
    if _queue_instance is None:
        _queue_instance = IngestQueue(max_workers=settings.ingest_workers)
    return _queue_instance


def enqueue_document_task(*args, **kwargs) -> None:
    from app.services.ingest_tasks import process_document_task

    queue = get_ingest_queue()
    future = queue.submit(process_document_task, *args, **kwargs)

    def _done_callback(fut: Future):
        try:
            fut.result()
        except Exception:  # noqa: BLE001
            logger.exception("Ingest job failed")

    future.add_done_callback(_done_callback)


def get_queue_stats() -> dict[str, int]:
    return get_ingest_queue().stats()


def shutdown_ingest_queue() -> None:
    global _queue_instance
    if _queue_instance is not None:
        _queue_instance.shutdown()
        _queue_instance = None
