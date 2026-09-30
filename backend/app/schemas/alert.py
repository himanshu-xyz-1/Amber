from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict

class AlertSource(str, Enum):
    PAGERDUTY = "PAGERDUTY"
    SENTRY = "SENTRY"
    DATADOG = "DATADOG"
    CLOUDWATCH = "CLOUDWATCH"
    PROMETHEUS = "PROMETHEUS"
    GENERIC = "GENERIC"

class WebhookPayload(BaseModel):
    source: AlertSource = Field(..., description="Source of the alert")
    raw_payload: Dict[str, Any] = Field(..., description="Raw payload from the external system")
    source_alert_id: Optional[str] = Field(None, description="ID of the alert in the source system")
    title: Optional[str] = Field(None, description="Title of the alert")

class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_id: Optional[UUID] = None
    source: AlertSource
    fingerprint: str
    raw_payload: Dict[str, Any]
    sanitized_payload: Optional[Dict[str, Any]] = None
    ingested_at: datetime

class WebhookAckResponse(BaseModel):
    status: str = Field(default="accepted", description="Status of the request")
    alert_id: UUID = Field(..., description="Internal ID of the ingested alert")
    message: str = Field(..., description="Acknowledgment message")
