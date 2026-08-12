"""
Audit API router for querying audit logs.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from apps.models.base import get_db
from apps.services.audit_service import AuditService
from apps.models.audit import AuditEventCategory
from apps.api.schemas import (
    AuditLogsRequest,
    AuditLogsResponse,
    AuditLogResponse,
    AuditStatsResponse,
)
from apps.utils.security import require_role, ClientRole

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/logs", response_model=AuditLogsResponse)
async def get_audit_logs(
    request: AuditLogsRequest,
    db: Session = Depends(get_db),
    auth=Depends(require_role([ClientRole.COORDINATOR, ClientRole.ENGINEER])),
):
    """
    Query audit logs with filters.
    
    Requires COORDINATOR or ENGINEER role.
    """
    try:
        audit_service = AuditService(db)
        
        # Convert category string to enum if provided
        event_category = None
        if request.event_category:
            try:
                event_category = AuditEventCategory(request.event_category)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid event category: {request.event_category}",
                )
        
        logs = audit_service.get_logs(
            organization_id=request.organization_id,
            event_category=event_category,
            start_date=request.start_date,
            end_date=request.end_date,
            limit=request.limit,
        )
        
        # Convert to response format
        log_responses = []
        for log in logs:
            log_responses.append(AuditLogResponse(
                id=log.id,
                event_category=log.event_category.value,
                event_type=log.event_type,
                actor_client_id=log.actor_client_id,
                organization_id=log.organization_id,
                outcome=log.outcome.value,
                severity=log.severity.value,
                created_at=log.created_at.isoformat() if log.created_at else None,
            ))
        
        return {
            "logs": log_responses,
            "total": len(log_responses),
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get audit logs: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get audit logs: {str(e)}",
        )


@router.get("/stats", response_model=AuditStatsResponse)
async def get_audit_stats(
    db: Session = Depends(get_db),
    auth=Depends(require_role([ClientRole.COORDINATOR, ClientRole.ENGINEER])),
):
    """
    Get audit statistics.
    
    Requires COORDINATOR or ENGINEER role.
    """
    try:
        audit_service = AuditService(db)
        stats = audit_service.get_statistics()
        
        return stats
    
    except Exception as e:
        logger.error(f"Failed to get audit stats: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get audit stats: {str(e)}",
        )
