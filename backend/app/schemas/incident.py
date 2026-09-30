from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict

class Severity(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"

class IncidentStatus(str, Enum):
    TRIGGERED = "TRIGGERED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATING = "INVESTIGATING"
    PROPOSED = "PROPOSED"
    EXECUTING = "EXECUTING"
    RESOLVED = "RESOLVED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"

class IncidentCreate(BaseModel):
    title: str = Field(..., description="Title of the incident")
    description: Optional[str] = Field(None, description="Detailed description of the incident")
    severity: Severity = Field(..., description="Severity level")
    source_service: Optional[str] = Field(None, description="Service where the incident originated")

class IncidentUpdate(BaseModel):
    title: Optional[str] = Field(None, description="Title of the incident")
    severity: Optional[Severity] = Field(None, description="Severity level")
    status: Optional[IncidentStatus] = Field(None, description="Current status of the incident")
    root_cause_summary: Optional[str] = Field(None, description="Summary of the root cause")
    remediation_plan: Optional[Dict[str, Any]] = Field(None, description="Proposed remediation steps")

class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    title: str
    description: Optional[str] = None
    severity: Severity
    status: IncidentStatus
    source_service: Optional[str] = None
    root_cause_summary: Optional[str] = None
    remediation_plan: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

class IncidentListResponse(BaseModel):
    total_count: int = Field(..., description="Total number of incidents")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of incidents per page")
    incidents: List[IncidentResponse] = Field(..., description="List of incidents")

class IncidentTimeline(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    incident_id: UUID
    event_type: str = Field(..., description="Type of the timeline event")
    description: str = Field(..., description="Description of the event")
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None
