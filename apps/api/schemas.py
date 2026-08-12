"""
Pydantic schemas for API request/response models.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from apps.models.job import JobStatus


# Scan schemas
class StartScanRequest(BaseModel):
    """Request to start a new scan."""
    organization_id: str = Field(..., description="Organization identifier")
    object_types: List[str] = Field(..., description="HubSpot object types to extract")
    access_token: str = Field(..., description="HubSpot OAuth access token")
    refresh_token: Optional[str] = Field(None, description="HubSpot OAuth refresh token")


class JobResponse(BaseModel):
    """Job response model."""
    id: int
    organization_id: str
    status: str
    object_types: List[str]
    entity_record_counts: Dict[str, int]
    created_at: Optional[str]
    updated_at: Optional[str]
    normalized_at: Optional[str]
    minio_uploaded_at: Optional[str]
    last_heartbeat: Optional[str]
    error_message: Optional[str]


class ScanListResponse(BaseModel):
    """Response for list scans."""
    scans: List[JobResponse]
    total: int


class ScanStatisticsResponse(BaseModel):
    """Scan statistics response."""
    total_scans: int
    running: int
    completed: int
    failed: int
    paused: int
    cancelled: int
    crashed: int


# Normalization schemas
class NormalizeRequest(BaseModel):
    """Request to normalize scan data."""
    output_format: str = Field(default="parquet", description="Output format (json or parquet)")
    upload_to_minio: bool = Field(default=True, description="Whether to upload to MinIO")


class NormalizeResponse(BaseModel):
    """Normalization response."""
    scan_id: int
    tables: List[str]
    status: str
    minio_objects: Optional[Dict[str, str]] = None


class TablesResponse(BaseModel):
    """Response for available tables."""
    scan_id: int
    tables: List[str]


class SupportedObjectsResponse(BaseModel):
    """Response for supported object types."""
    object_types: List[str]


# Credentials schemas
class ValidateCredentialsRequest(BaseModel):
    """Request to validate HubSpot credentials."""
    access_token: str = Field(..., description="HubSpot OAuth access token")
    refresh_token: Optional[str] = Field(None, description="HubSpot OAuth refresh token")


class ValidateCredentialsResponse(BaseModel):
    """Credentials validation response."""
    valid: bool
    message: str
    token_info: Optional[Dict[str, Any]] = None


# Maintenance schemas
class CleanupRequest(BaseModel):
    """Request to cleanup old data."""
    days_old: int = Field(default=30, description="Delete data older than this many days")


class CleanupResponse(BaseModel):
    """Cleanup response."""
    deleted_jobs: int
    deleted_audit_logs: int
    deleted_failed_calls: int


class DetectCrashedRequest(BaseModel):
    """Request to detect crashed jobs."""
    timeout_minutes: int = Field(default=30, description="Minutes without heartbeat to consider crashed")


class DetectCrashedResponse(BaseModel):
    """Detect crashed response."""
    crashed_jobs: List[int]
    count: int


# Audit schemas
class AuditLogsRequest(BaseModel):
    """Request for audit logs."""
    organization_id: Optional[str] = None
    event_category: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    limit: int = Field(default=100, le=1000)


class AuditLogResponse(BaseModel):
    """Single audit log entry."""
    id: int
    event_category: str
    event_type: str
    actor_client_id: Optional[str]
    organization_id: Optional[str]
    outcome: str
    severity: str
    created_at: str


class AuditLogsResponse(BaseModel):
    """Response for audit logs."""
    logs: List[AuditLogResponse]
    total: int


class AuditStatsResponse(BaseModel):
    """Audit statistics response."""
    total_events: int
    by_category: Dict[str, int]
    by_outcome: Dict[str, int]
    by_severity: Dict[str, int]
