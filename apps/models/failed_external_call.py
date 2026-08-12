"""Failed external call model for dead letter queue."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Index
from apps.models.base import Base


class FailedExternalCall(Base):
    """Dead letter queue table for failed external API calls."""
    __tablename__ = "failed_external_calls"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Target service information
    target_service = Column(String(100), nullable=False, index=True)
    operation = Column(String(255), nullable=False)
    
    # Request information (scrubbed of sensitive data)
    payload = Column(Text, nullable=True)
    
    # Failure information
    attempts = Column(Integer, nullable=False)
    error_message = Column(Text, nullable=False)
    error_details = Column(JSON, nullable=True)
    
    # Context
    organization_id = Column(String(255), nullable=True, index=True)
    scan_id = Column(Integer, nullable=True, index=True)
    
    # Timestamp
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Indexes
    __table_args__ = (
        Index("idx_dlq_service_created", "target_service", "created_at"),
    )
    
    def __repr__(self) -> str:
        return f"<FailedExternalCall(id={self.id}, service={self.target_service}, operation={self.operation})>"
