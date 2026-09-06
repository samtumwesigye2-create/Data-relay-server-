from __future__ import annotations

import json
import os
import time
import urllib.request

import app as core

ATLAS_BASE_URL = os.getenv("ATLAS_BASE_URL", "").rstrip("/")
POLL_SECONDS = int(os.getenv("ATLAS_POLL_SECONDS", "60"))


def collect_once() -> None:
    if not ATLAS_BASE_URL:
        return
    started = time.perf_counter()
    status = "offline"
    severity = "warning"
    payload = {"service": "UNG-ATLAS"}
    try:
        with urllib.request.urlopen(ATLAS_BASE_URL + "/health", timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            status = "online" if response.status == 200 else "degraded"
            severity = "info" if response.status == 200 else "warning"
            payload.update({"http_status": response.status, "health": data})
    except Exception as exc:
        payload.update({"error": type(exc).__name__})

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    event = core.EventIn(
        category="system_metric",
        source="atlas",
        severity=severity,
        actor="UNG-PULSAR",
        action="health_probe",
        resource="UNG-ATLAS/health",
        status=status,
        duration_ms=duration_ms,
        payload=payload,
    )
    connection = core.conn()
    try:
        core.insert_event(connection, event)
        connection.commit()
    finally:
        connection.close()


while True:
    try:
        collect_once()
    except Exception:
        pass
    time.sleep(POLL_SECONDS)
