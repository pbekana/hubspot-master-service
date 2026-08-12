"""
Maintenance API router for system maintenance operations.
"""
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from apps.models.base import get_db
from apps.services.extraction_service import ExtractionService
from apps.services.audit_service import AuditService
from apps.models.failed_external_call import FailedExternalCall
from apps.api.schemas import (
    CleanupRequest,
    CleanupResponse,
    DetectCrashedRequest,
    DetectCrashedResponse,
)
from apps.utils.security import require_role, ClientRole

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/detect-crashed", response_model=DetectCrashedResponse)
async def detect_crashed(
    request: DetectCrashedRequest,
    db: Session = Depends(get_db),
    auth=Depends(require_role([ClientRole.COORDINATOR])),
):
    """
    Detect crashed jobs based on stale heartbeat.
    
    Requires COORDINATOR role.
    """
    try:
        service = ExtractionService(db)
        crashed_jobs = service.detect_crashed_jobs(timeout_minutes=request.timeout_minutes)
        
        job_ids = [job.id for job in crashed_jobs]
        
        logger.info(f"Detected {len(job_ids)} crashed jobs")
        
        return {
            "crashed_jobs": job_ids,
            "count": len(job_ids),
        }
    
    except Exception as e:
        logger.error(f"Failed to detect crashed jobs: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to detect crashed jobs: {str(e)}",
        )


@router.post("/cleanup", response_model=CleanupResponse)
async def cleanup(
    request: CleanupRequest,
    db: Session = Depends(get_db),
    auth=Depends(require_role([ClientRole.COORDINATOR])),
):
    """
    Cleanup old data from database.
    
    Requires COORDINATOR role.
    """
    try:
        from apps.models.job import Job
        
        cutoff_date = datetime.utcnow() - timedelta(days=request.days_old)
        
        # Delete old completed/failed/cancelled jobs
        deleted_jobs = db.query(Job).filter(
            Job.updated_at < cutoff_date,
            Job.status.in_(["COMPLETED", "FAILED", "CANCELLED"]),
        ).delete(synchronize_session=False)
        
        # Delete old audit logs
        audit_service = AuditService(db)
        deleted_audit_logs = audit_service.cleanup_old_logs(days_old=request.days_old)
        
        # Delete old failed external calls
        deleted_failed_calls = db.query(FailedExternalCall).filter(
            FailedExternalCall.created_at < cutoff_date
        ).delete(synchronize_session=False)
        
        db.commit()
        
        logger.info(
            f"Cleanup completed: {deleted_jobs} jobs, "
            f"{deleted_audit_logs} audit logs, "
            f"{deleted_failed_calls} failed calls"
        )
        
        return {
            "deleted_jobs": deleted_jobs,
            "deleted_audit_logs": deleted_audit_logs,
            "deleted_failed_calls": deleted_failed_calls,
        }
    
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to cleanup: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup: {str(e)}",
        )
