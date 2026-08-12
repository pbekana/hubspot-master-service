"""Checkpoint model for tracking pagination state."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from apps.models.base import Base


class Checkpoint(Base):
    """Checkpoint table for tracking pagination state per job and object type."""
    __tablename__ = "job_checkpoints"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    object_type = Column(String(100), nullable=False)
    cursor = Column(String(500), nullable=True)  # HubSpot pagination cursor
    records_processed = Column(Integer, nullable=False, default=0)
    last_updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        Index("idx_job_object", "job_id", "object_type", unique=True),
    )
    
    def __repr__(self) -> str:
        return f"<Checkpoint(job_id={self.job_id}, object_type={self.object_type}, records={self.records_processed})>"
