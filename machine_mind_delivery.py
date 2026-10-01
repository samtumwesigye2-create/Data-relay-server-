from __future__ import annotations
import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import app as core

MACHINE_MIND_BASE_URL = os.getenv("MACHINE_MIND_BASE_URL", "").rstrip("/")
POLL_SECONDS = max(0.5, float(os.getenv("PULSAR_MACHINE_MIND_POLL_SECONDS", "1.0")))
DELIVERY_TIMEOUT = max(1.0, float(os.getenv("PULSAR_MACHINE_MIND_TIMEOUT", "8.0")))

_started = False
_lock = threading.Lock()

def _due(next_attempt_at: str | None) -> bool:
    if not next_attempt_at:
        return True
    try:
        return datetime.fromisoformat(next_attempt_at).timestamp() <= time.time()
    except Exception:
        return True

def _deliver(row: dict) -> None:
    payload = json.loads(row.get("payload_json") or "{}")
    body = payload.get("body") if isinstance(payload, dict) else {}
    envelope = {
        "source_system": row["source"],
        "target_system": row["target"],
        "message_type": row["event_type"],
        "payload": body if isinstance(body, dict) else {"value": body},
        "message_id": row["message_id"],
        "correlation_id": payload.get("correlation_id") if isinstance(payload, dict) else None,
        "trace_id": payload.get("trace_id") if isinstance(payload, dict) else None,
        "schema_version": (payload.get("schema_version") if isinstance(payload, dict) else None) or "1.0",
        "priority": int(row.get("priority") or 50),
        "classification": (payload.get("classification") if isinstance(payload, dict) else None) or "internal",
    }
    req = urllib.request.Request(
        MACHINE_MIND_BASE_URL + "/v1/nexus/inbound",
        data=json.dumps(envelope, separators=(",", ":")).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "UNG-PULSAR/1.2-machine-mind"},
    )
    with urllib.request.urlopen(req, timeout=DELIVERY_TIMEOUT) as response:
        code = int(response.status)
        if not 200 <= code < 300:
            raise RuntimeError(f"http_{code}")

def _mark_delivered(message_id: str) -> None:
    c = core.delivery_store.c()
    try:
        c.execute(
            "UPDATE delivery_queue SET status='delivered',last_error=NULL,next_attempt_at=? WHERE message_id=?",
            (datetime.now(timezone.utc).isoformat(), message_id),
        )
        c.commit()
    finally:
        c.close()

def _mark_failed(row: dict, error: str) -> None:
    attempts = int(row.get("attempts") or 0) + 1
    max_attempts = int(row.get("max_attempts") or 5)
    c = core.delivery_store.c()
    try:
        if attempts >= max_attempts:
            record = dict(row)
            record["attempts"] = attempts
            record["status"] = "dead-letter"
            record["last_error"] = error
            c.execute(
                "INSERT OR REPLACE INTO delivery_dlq(message_id,record_json) VALUES(?,?)",
                (row["message_id"], json.dumps(record, separators=(",", ":"))),
            )
            c.execute("DELETE FROM delivery_queue WHERE message_id=?", (row["message_id"],))
        else:
            delay = min(300, 2 ** max(0, attempts - 1))
            next_at = datetime.fromtimestamp(time.time() + delay, timezone.utc).isoformat()
            c.execute(
                "UPDATE delivery_queue SET attempts=?,status='retry',next_attempt_at=?,last_error=? WHERE message_id=?",
                (attempts, next_at, error, row["message_id"]),
            )
        c.commit()
    finally:
        c.close()

def _run() -> None:
    while True:
        try:
            if MACHINE_MIND_BASE_URL:
                rows = core.delivery_store.list_queue(limit=200)
                for row in rows:
                    if row.get("target") != "MACHINE-MIND":
                        continue
                    if row.get("status") not in {"queued", "retry"}:
                        continue
                    if not _due(row.get("next_attempt_at")):
                        continue
                    try:
                        _deliver(row)
                        _mark_delivered(row["message_id"])
                        print(f"PULSAR_DELIVERY target=MACHINE-MIND message_id={row['message_id']} status=delivered", flush=True)
                    except Exception as exc:
                        _mark_failed(row, type(exc).__name__)
                        print(f"PULSAR_DELIVERY target=MACHINE-MIND message_id={row['message_id']} status=failed error={type(exc).__name__}", flush=True)
        except Exception as exc:
            print(f"PULSAR_MACHINE_MIND_WORKER error={type(exc).__name__}", flush=True)
        time.sleep(POLL_SECONDS)

def start() -> None:
    global _started
    with _lock:
        if _started:
            return
        _started = True
        threading.Thread(target=_run, name="pulsar-machine-mind-worker", daemon=True).start()
