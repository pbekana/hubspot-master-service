"""Audit log model for tracking system events."""
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Enum as SQLEnum, JSON, Text, Index
from apps.models.base import Base


class AuditEventCategory(str, enum.Enum):
    """Audit event categories."""
    AUTHENTICATION = "AUTHENTICATION"
    AUTHORIZATION = "AUTHORIZATION"
    JOB_LIFECYCLE = "JOB_LIFECYCLE"
    DATA_EXTRACTION = "DATA_EXTRACTION"
    DATA_NORMALIZATION = "DATA_NORMALIZATION"
    DATA_UPLOAD = "DATA_UPLOAD"
    SYSTEM = "SYSTEM"
    API_REQUEST = "API_REQUEST"


class AuditOutcome(str, enum.Enum):
    """Audit event outcomes."""
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    PARTIAL = "PARTIAL"


class AuditSeverity(str, enum.Enum):
    """Audit event severity levels."""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AuditLog(Base):
    """Audit log table for tracking system events."""
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Event classification
    event_category = Column(SQLEnum(AuditEventCategory), nullable=False, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    
    # Actor information
    actor_client_id = Column(String(255), nullable=True)
    actor_role = Column(String(50), nullable=True)
    
    # Resource information
    organization_id = Column(String(255), nullable=True, index=True)
    entity_type = Column(String(100), nullable=True)
    resource_type = Column(String(100), nullable=True)
    resource_id = Column(String(255), nullable=True)
    
    # Request information
    http_method = Column(String(10), nullable=True)
    endpoint = Column(String(500), nullable=True)
    request_ip = Column(String(45), nullable=True)
    
    # Outcome
    status_code = Column(Integer, nullable=True)
    outcome = Column(SQLEnum(AuditOutcome), nullable=False)
    severity = Column(SQLEnum(AuditSeverity), nullable=False, default=AuditSeverity.INFO)
    
    # Details
    error_detail = Column(Text, nullable=True)
    extra_metadata = Column(JSON, nullable=True)
    
    # Timestamp
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Indexes
    __table_args__ = (
        Index("idx_audit_org_category", "organization_id", "event_category"),
        Index("idx_audit_created", "created_at"),
    )
    
    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, category={self.event_category}, type={self.event_type})>"
