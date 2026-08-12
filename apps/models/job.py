"""Job model for tracking extraction jobs."""
import enum
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import Column, Integer, String, DateTime, Enum as SQLEnum, JSON, Text
from apps.models.base import Base


class JobStatus(str, enum.Enum):
    """Job status enumeration."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    RESUMING = "RESUMING"
    NORMALIZING = "NORMALIZING"
    UPLOADING_TO_MINIO = "UPLOADING_TO_MINIO"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    CRASHED = "CRASHED"


class Job(Base):
    """Job table for tracking extraction jobs."""
    __tablename__ = "jobs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(String(255), nullable=False, index=True)
    status = Column(SQLEnum(JobStatus), nullable=False, default=JobStatus.PENDING, index=True)
    object_types = Column(JSON, nullable=False)  # List of object types to extract
    entity_record_counts = Column(JSON, nullable=True)  # Dict mapping object_type -> count
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    normalized_at = Column(DateTime, nullable=True)
    minio_uploaded_at = Column(DateTime, nullable=True)
    last_heartbeat = Column(DateTime, nullable=True)
    
    # Error information
    error_message = Column(Text, nullable=True)
    error_details = Column(JSON, nullable=True)
    
    # OAuth credentials (encrypted or stored securely)
    access_token_encrypted = Column(Text, nullable=True)
    refresh_token_encrypted = Column(Text, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    
    def __repr__(self) -> str:
        return f"<Job(id={self.id}, org={self.organization_id}, status={self.status})>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary."""
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "status": self.status.value,
            "object_types": self.object_types,
            "entity_record_counts": self.entity_record_counts or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "normalized_at": self.normalized_at.isoformat() if self.normalized_at else None,
            "minio_uploaded_at": self.minio_uploaded_at.isoformat() if self.minio_uploaded_at else None,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "error_message": self.error_message,
        }
