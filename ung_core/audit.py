import json
import logging

from .contracts import AuditEvent

logger = logging.getLogger("ung.audit")


def emit_audit(event: AuditEvent) -> None:
    """Emit structured audit data for Sentinel/Data Relay collectors."""
    logger.info(json.dumps(event.model_dump(mode="json"), separators=(",", ":")))
