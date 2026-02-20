import time
from threading import Event

from app.services.ingest_queue import IngestQueue


def test_ingest_queue_respects_worker_limit():
    queue = IngestQueue(max_workers=1)
    blocker = Event()

    def _task():
        blocker.wait(timeout=2)
        return 1

    f1 = queue.submit(_task)
    f2 = queue.submit(_task)
    time.sleep(0.1)
    stats = queue.stats()
    assert stats["running_workers"] <= 1
    assert stats["queued_jobs"] >= 1

    blocker.set()
    assert f1.result(timeout=3) == 1
    assert f2.result(timeout=3) == 1

    queue.shutdown()
