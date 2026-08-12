"""
Audit service for logging system events.
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from apps.models.audit import (
    AuditLog,
    AuditEventCategory,
    AuditOutcome,
    AuditSeverity,
)

logger = logging.getLogger(__name__)


class AuditService:
    """Service for audit logging."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def log_event(
        self,
        event_category: AuditEventCategory,
        event_type: str,
        outcome: AuditOutcome,
        severity: AuditSeverity = AuditSeverity.INFO,
        actor_client_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        organization_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        http_method: Optional[str] = None,
        endpoint: Optional[str] = None,
        request_ip: Optional[str] = None,
        status_code: Optional[int] = None,
        error_detail: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[AuditLog]:
        """
        Log an audit event.
        
        Args:
            event_category: Category of the event
            event_type: Type of the event
            outcome: Outcome of the event
            severity: Severity level
            actor_client_id: Who performed the action
            actor_role: Role of the actor
            organization_id: Organization involved
            entity_type: Type of entity
            resource_type: Type of resource
            resource_id: Resource identifier
            http_method: HTTP method
            endpoint: API endpoint
            request_ip: Client IP address
            status_code: HTTP status code
            error_detail: Error detail if failed
            extra_metadata: Additional metadata
        
        Returns:
            Created AuditLog or None if failed
        """
        try:
            audit_log = AuditLog(
                event_category=event_category,
                event_type=event_type,
                outcome=outcome,
                severity=severity,
                actor_client_id=actor_client_id,
                actor_role=actor_role,
                organization_id=organization_id,
                entity_type=entity_type,
                resource_type=resource_type,
                resource_id=resource_id,
                http_method=http_method,
                endpoint=endpoint,
                request_ip=request_ip,
                status_code=status_code,
                error_detail=error_detail,
                extra_metadata=extra_metadata,
                created_at=datetime.utcnow(),
            )
            
            self.db.add(audit_log)
            self.db.commit()
            
            logger.debug(
                f"Audit log created: {event_category.value}/{event_type} - {outcome.value}"
            )
            
            return audit_log
            
        except Exception as e:
            # Don't let audit failure break the main operation
            logger.error(f"Failed to create audit log: {str(e)}", exc_info=True)
            try:
                self.db.rollback()
            except Exception:
                pass
            return None
    
    def get_logs(
        self,
        organization_id: Optional[str] = None,
        event_category: Optional[AuditEventCategory] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AuditLog]:
        """
        Query audit logs with filters.
        
        Args:
            organization_id: Filter by organization
            event_category: Filter by category
            start_date: Start date filter
            end_date: End date filter
            limit: Maximum number of logs to return
        
        Returns:
            List of audit logs
        """
        query = self.db.query(AuditLog)
        
        if organization_id:
            query = query.filter(AuditLog.organization_id == organization_id)
        
        if event_category:
            query = query.filter(AuditLog.event_category == event_category)
        
        if start_date:
            query = query.filter(AuditLog.created_at >= start_date)
        
        if end_date:
            query = query.filter(AuditLog.created_at <= end_date)
        
        return query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get audit statistics.
        
        Returns:
            Dictionary with statistics
        """
        total_events = self.db.query(AuditLog).count()
        
        # Count by category
        by_category = {}
        for category in AuditEventCategory:
            count = self.db.query(AuditLog).filter(
                AuditLog.event_category == category
            ).count()
            by_category[category.value] = count
        
        # Count by outcome
        by_outcome = {}
        for outcome in AuditOutcome:
            count = self.db.query(AuditLog).filter(
                AuditLog.outcome == outcome
            ).count()
            by_outcome[outcome.value] = count
        
        # Count by severity
        by_severity = {}
        for severity in AuditSeverity:
            count = self.db.query(AuditLog).filter(
                AuditLog.severity == severity
            ).count()
            by_severity[severity.value] = count
        
        return {
            "total_events": total_events,
            "by_category": by_category,
            "by_outcome": by_outcome,
            "by_severity": by_severity,
        }
    
    def cleanup_old_logs(self, days_old: int = 30) -> int:
        """
        Delete audit logs older than specified days.
        
        Args:
            days_old: Delete logs older than this many days
        
        Returns:
            Number of logs deleted
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        deleted_count = self.db.query(AuditLog).filter(
            AuditLog.created_at < cutoff_date
        ).delete()
        
        self.db.commit()
        
        logger.info(f"Deleted {deleted_count} audit logs older than {days_old} days")
        return deleted_count


# Helper function to create audit service
def create_audit_service(db: Session) -> AuditService:
    """Create audit service instance."""
    return AuditService(db)
