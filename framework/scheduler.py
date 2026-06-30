from threading import Lock, Thread
from time import monotonic, sleep

from framework.collector import snapshot_system
from framework.database import cleanup_old_records


COLLECTION_INTERVAL_SECONDS = 5
MAINTENANCE_INTERVAL_SECONDS = 3600
_worker_started = False
_worker_lock = Lock()


def _run_monitor():
    last_maintenance_time = 0

    while True:
        snapshot_system()
        current_time = monotonic()
        if current_time - last_maintenance_time >= MAINTENANCE_INTERVAL_SECONDS:
            cleanup_old_records()
            last_maintenance_time = current_time

        sleep(COLLECTION_INTERVAL_SECONDS)


def start_background_monitor():
    global _worker_started

    with _worker_lock:
        if _worker_started:
            return

        worker = Thread(target=_run_monitor, daemon=True)
        worker.start()
        _worker_started = True
