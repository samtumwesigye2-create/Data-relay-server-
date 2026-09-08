"""Non-blocking UNG-PULSAR/Data Relay -> UNG-ZEUS storage handoff."""
import base64
import hashlib
import hmac
import json
import os
import time
import uuid
import urllib.error
import urllib.request
from typing import Any, Dict

ZEUS_URL = os.environ.get("ZEUS_URL", "").rstrip("/")
ZEUS_PULSAR_SHARED_SECRET = os.environ.get("ZEUS_PULSAR_SHARED_SECRET", "")
ZEUS_TIMEOUT_SECONDS = float(os.environ.get("ZEUS_TIMEOUT_SECONDS", "5"))
ZEUS_INLINE_MAX_BYTES = int(os.environ.get("ZEUS_INLINE_MAX_BYTES", str(25 * 1024 * 1024)))


def enabled() -> bool:
    return bool(ZEUS_URL and ZEUS_PULSAR_SHARED_SECRET)


def _canonical(body: bytes, timestamp: str, event_id: str) -> bytes:
    return timestamp.encode() + b"." + event_id.encode() + b"." + body


def _signature(body: bytes, timestamp: str, event_id: str) -> str:
    digest = hmac.new(ZEUS_PULSAR_SHARED_SECRET.encode(), _canonical(body, timestamp, event_id), hashlib.sha256).hexdigest()
    return "sha256=" + digest


def handoff_bytes(*, source: str, object_key: str, payload: bytes,
                  namespace: str = "", content_type: str = "application/octet-stream",
                  classification: str = "internal", priority: int = 50,
                  trace_id: str = "", metadata: Dict[str, Any] | None = None,
                  event_id: str = "") -> Dict[str, Any]:
    if not enabled():
        return {"accepted": False, "reason": "zeus_not_configured"}
    if not payload:
        return {"accepted": False, "reason": "empty_payload"}
    if len(payload) > ZEUS_INLINE_MAX_BYTES:
        return {"accepted": False, "reason": "payload_too_large", "bytes": len(payload)}
    eid = event_id or str(uuid.uuid4())
    ts = str(int(time.time()))
    envelope = {
        "event_id": eid, "source": source, "object_key": object_key,
        "namespace": namespace or source.lower(),
        "payload_b64": base64.b64encode(payload).decode("ascii"),
        "content_type": content_type, "classification": classification,
        "priority": max(0, min(100, int(priority))), "trace_id": trace_id,
        "timestamp": int(ts), "metadata": metadata or {},
    }
    body = json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode()
    req = urllib.request.Request(
        ZEUS_URL + "/integrations/pulsar/ingest", data=body, method="POST",
        headers={"Content-Type": "application/json", "X-Pulsar-Timestamp": ts,
                 "X-Pulsar-Event-Id": eid, "X-Pulsar-Signature": _signature(body, ts, eid)},
    )
    try:
        with urllib.request.urlopen(req, timeout=ZEUS_TIMEOUT_SECONDS) as resp:
            result = json.loads(resp.read().decode())
            result["http_status"] = resp.status
            return result
    except urllib.error.HTTPError as exc:
        return {"accepted": False, "reason": "zeus_http_error", "http_status": exc.code,
                "detail": exc.read(1024).decode(errors="replace")}
    except Exception as exc:
        # PULSAR/Data Relay must continue operating if ZEUS is unavailable.
        return {"accepted": False, "reason": "zeus_unavailable", "error": str(exc)[:300]}
