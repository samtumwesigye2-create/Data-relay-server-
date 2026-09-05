from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EnterpriseEvent(BaseModel):
    message_id: UUID = Field(default_factory=uuid4)
    correlation_id: UUID = Field(default_factory=uuid4)
    source_system: str = Field(min_length=2, max_length=64)
    destination_system: str | None = Field(default=None, max_length=64)
    event_type: str = Field(min_length=3, max_length=128)
    schema_version: str = Field(default="1.0")
    priority: Literal["critical", "high", "normal", "low"] = "normal"
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any]


class ServiceHealth(BaseModel):
    service: str
    status: Literal["ok", "degraded", "down"]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict[str, Any] = Field(default_factory=dict)


class AuditEvent(BaseModel):
    audit_id: UUID = Field(default_factory=uuid4)
    actor_type: Literal["user", "service", "system"]
    actor_id: str
    action: str
    resource_type: str
    resource_id: str | None = None
    outcome: Literal["success", "denied", "failed"]
    correlation_id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)
