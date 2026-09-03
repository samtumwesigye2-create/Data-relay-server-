from __future__ import annotations
import os
import time
import httpx
from relay_queue import RelayQueue

BACKUP_HEALTH_URL = os.getenv("BACKUP_HEALTH_URL", "").strip()
BACKUP_NAME = os.getenv("BACKUP_NAME", "backup").strip() or "backup"
INTERVAL = max(30, int(os.getenv("BACKUP_CHECK_INTERVAL_SECONDS", "60")))
TIMEOUT = max(2.0, float(os.getenv("BACKUP_CHECK_TIMEOUT_SECONDS", "8")))


def collect_once(queue: RelayQueue) -> None:
    if not BACKUP_HEALTH_URL:
        return
    started = time.perf_counter()
    status = "unavailable"
    status_code = None
    error = ""
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
            r = client.get(BACKUP_HEALTH_URL, headers={"Accept": "application/json"})
        status_code = r.status_code
        status = "healthy" if 200 <= r.status_code < 400 else "degraded"
    except Exception as exc:
        error = type(exc).__name__

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    queue.enqueue({
        "category": "system_metric",
        "source": "backup",
        "severity": "info" if status == "healthy" else "error",
        "actor": "backup-health-collector",
        "action": "backup_health_check",
        "resource": BACKUP_NAME,
        "status": status,
        "duration_ms": duration_ms,
        "payload": {
            "component": "backup",
            "health": status,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "error_type": error,
        },
    })


def main() -> None:
    queue = RelayQueue()
    while True:
        collect_once(queue)
        queue.flush()
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
