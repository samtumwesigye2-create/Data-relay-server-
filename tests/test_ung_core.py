from ung_core.contracts import AuditEvent, EnterpriseEvent
from ung_core.health import get_health


def test_enterprise_event_defaults():
    event = EnterpriseEvent(source_system="UGASHIP", event_type="shipment.updated", payload={"id": "S1"})
    assert event.schema_version == "1.0"
    assert event.priority == "normal"
    assert event.message_id
    assert event.correlation_id


def test_audit_event():
    event = AuditEvent(
        actor_type="service",
        actor_id="data-relay",
        action="publish",
        resource_type="event",
        outcome="success",
    )
    assert event.outcome == "success"


def test_health_shape():
    health = get_health()
    assert health.service
    assert health.status in {"ok", "degraded", "down"}
