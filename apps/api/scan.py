"""
Scan API router for job management endpoints.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from apps.models.base import get_db
from apps.models.job import JobStatus
from apps.services.extraction_service import ExtractionService
from apps.api.schemas import (
    StartScanRequest,
    JobResponse,
    ScanListResponse,
    ScanStatisticsResponse,
)
from apps.utils.security import require_role, ClientRole

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/start", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def start_scan(
    request: StartScanRequest,
    db: Session = Depends(get_db),
    auth=Depends(require_role([ClientRole.COORDINATOR])),
):
    """
    Start a new HubSpot data extraction scan.
    
    Requires COORDINATOR role.
    """
    try:
        service = ExtractionService(db)
        job = service.start_scan(
            organization_id=request.organization_id,
            object_types=request.object_types,
            access_token=request.access_token,
            refresh_token=request.refresh_token,
        )
        logger.info(f"Started scan job {job.id} for organization {request.organization_id}")
        return job.to_dict()
    except Exception as e:
        logger.error(f"Failed to start scan: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start scan: {str(e)}",
        )


@router.get("/{scan_id}/status", response_model=JobResponse)
async def get_scan_status(
    scan_id: int,
    db: Session = Depends(get_db),
    auth=Depends(require_role([ClientRole.COORDINATOR, ClientRole.ENGINEER])),
):
    """
    Get the status of a specific scan.
    
    Requires COORDINATOR or ENGINEER role.
    """
    try:
        service = ExtractionService(db)
        job = service.get_scan_status(scan_id)
        return job.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get scan status: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get scan status: {str(e)}",
        )


@router.post("/{scan_id}/pause", response_model=JobResponse)
async def pause_scan(
    scan_id: int,
    db: Session = Depends(get_db),
    auth=Depends(require_role([ClientRole.COORDINATOR])),
):
    """
    Pause a running scan.
    
    Requires COORDINATOR role.
    """
    try:
        service = ExtractionService(db)
        job = service.pause_scan(scan_id)
        logger.info(f"Paused scan job {scan_id}")
        return job.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to pause scan: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pause scan: {str(e)}",
        )


@router.post("/{scan_id}/resume", response_model=JobResponse)
async def resume_scan(
    scan_id: int,
    db: Session = Depends(get_db),
    auth=Depends(require_role([ClientRole.COORDINATOR])),
):
    """
    Resume a paused scan.
    
    Requires COORDINATOR role.
    """
    try:
        service = ExtractionService(db)
        job = service.resume_scan(scan_id)
        logger.info(f"Resumed scan job {scan_id}")
        return job.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to resume scan: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume scan: {str(e)}",
        )


@router.post("/{scan_id}/cancel", response_model=JobResponse)
async def cancel_scan(
    scan_id: int,
    db: Session = Depends(get_db),
    auth=Depends(require_role([ClientRole.COORDINATOR])),
):
    """
    Cancel a scan.
    
    Requires COORDINATOR role.
    """
    try:
        service = ExtractionService(db)
        job = service.cancel_scan(scan_id)
        logger.info(f"Cancelled scan job {scan_id}")
        return job.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to cancel scan: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel scan: {str(e)}",
        )


@router.get("/list", response_model=ScanListResponse)
async def list_scans(
    organization_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    auth=Depends(require_role([ClientRole.COORDINATOR, ClientRole.ENGINEER])),
):
    """
    List scans with optional filters.
    
    Requires COORDINATOR or ENGINEER role.
    """
    try:
        service = ExtractionService(db)
        
        # Convert status string to enum if provided
        status_enum = None
        if status:
            try:
                status_enum = JobStatus(status)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status: {status}",
                )
        
        jobs = service.list_scans(
            organization_id=organization_id,
            status=status_enum,
            limit=limit,
        )
        
        scans = [job.to_dict() for job in jobs]
        return {"scans": scans, "total": len(scans)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list scans: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list scans: {str(e)}",
        )


@router.get("/statistics", response_model=ScanStatisticsResponse)
async def get_statistics(
    db: Session = Depends(get_db),
    auth=Depends(require_role([ClientRole.COORDINATOR, ClientRole.ENGINEER])),
):
    """
    Get scan statistics.
    
    Requires COORDINATOR or ENGINEER role.
    """
    try:
        from apps.models.job import Job
        
        total_scans = db.query(Job).count()
        running = db.query(Job).filter(Job.status == JobStatus.RUNNING).count()
        completed = db.query(Job).filter(Job.status == JobStatus.COMPLETED).count()
        failed = db.query(Job).filter(Job.status == JobStatus.FAILED).count()
        paused = db.query(Job).filter(Job.status == JobStatus.PAUSED).count()
        cancelled = db.query(Job).filter(Job.status == JobStatus.CANCELLED).count()
        crashed = db.query(Job).filter(Job.status == JobStatus.CRASHED).count()
        
        return {
            "total_scans": total_scans,
            "running": running,
            "completed": completed,
            "failed": failed,
            "paused": paused,
            "cancelled": cancelled,
            "crashed": crashed,
        }
    except Exception as e:
        logger.error(f"Failed to get statistics: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get statistics: {str(e)}",
        )


@router.delete("/{scan_id}/remove", status_code=status.HTTP_204_NO_CONTENT)
async def remove_scan(
    scan_id: int,
    db: Session = Depends(get_db),
    auth=Depends(require_role([ClientRole.COORDINATOR])),
):
    """
    Remove a scan and its checkpoints.
    
    Requires COORDINATOR role.
    """
    try:
        service = ExtractionService(db)
        service.remove_scan(scan_id)
        logger.info(f"Removed scan job {scan_id}")
        return None
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to remove scan: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove scan: {str(e)}",
        )
