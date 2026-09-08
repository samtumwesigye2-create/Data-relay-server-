"""PULSAR durable-delivery primitives.
PULSAR owns transport reliability: idempotency, retry scheduling, DLQ and fan-out planning.
Storage adapter is deliberately injected so production can use the existing durable backend.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Protocol
from uuid import uuid4

@dataclass
class Delivery:
    source: str
    targets: list[str]
    event_type: str
    payload: dict[str, Any]
    message_id: str = field(default_factory=lambda: str(uuid4()))
    idempotency_key: str | None = None
    priority: int = 50
    attempts: int = 0
    max_attempts: int = 5
    status: str = "queued"
    next_attempt_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_error: str | None = None

class DeliveryStore(Protocol):
    def seen(self, key: str) -> bool: ...
    def save(self, delivery: Delivery) -> None: ...
    def dead_letter(self, delivery: Delivery) -> None: ...

class DeliveryPlanner:
    def __init__(self, store: DeliveryStore):
        self.store = store

    def enqueue(self, delivery: Delivery) -> bool:
        key = delivery.idempotency_key or delivery.message_id
        if self.store.seen(key):
            return False
        delivery.priority = max(0, min(100, int(delivery.priority)))
        self.store.save(delivery)
        return True

    def retry(self, delivery: Delivery, error: str) -> Delivery:
        delivery.attempts += 1
        delivery.last_error = error
        if delivery.attempts >= delivery.max_attempts:
            delivery.status = "dead-letter"
            self.store.dead_letter(delivery)
            return delivery
        delay = min(300, 2 ** max(0, delivery.attempts - 1))
        delivery.status = "retry"
        delivery.next_attempt_at = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
        self.store.save(delivery)
        return delivery

    @staticmethod
    def fanout(source: str, targets: list[str], event_type: str, payload: dict[str, Any], **kwargs) -> list[Delivery]:
        unique = list(dict.fromkeys(t for t in targets if t and t != source))
        return [Delivery(source=source, targets=[target], event_type=event_type, payload=payload, **kwargs) for target in unique]
