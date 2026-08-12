"""
Normalization API router for data transformation endpoints.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from apps.models.base import get_db
from apps.services.normalization_service import NormalizationService
from apps.api.schemas import (
    NormalizeRequest,
    NormalizeResponse,
    TablesResponse,
    SupportedObjectsResponse,
)
from apps.utils.security import require_role, ClientRole

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/{scan_id}/normalize", response_model=NormalizeResponse)
async def normalize_scan(
    scan_id: int,
    request: NormalizeRequest,
    db: Session = Depends(get_db),
    auth=Depends(require_role([ClientRole.COORDINATOR])),
):
    """
    Normalize extracted data for a scan.
    
    Requires COORDINATOR role.
    """
    try:
        service = NormalizationService(db)
        result = await service.normalize_scan(
            scan_id=scan_id,
            output_format=request.output_format,
            upload_to_minio=request.upload_to_minio,
        )
        
        logger.info(f"Normalized scan {scan_id}")
        
        return {
            "scan_id": result["scan_id"],
            "tables": result["tables"],
            "status": result["status"],
            "minio_objects": result.get("minio_objects"),
        }
    
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to normalize scan: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to normalize scan: {str(e)}",
        )


@router.get("/{scan_id}/tables", response_model=TablesResponse)
async def get_tables(
    scan_id: int,
    db: Session = Depends(get_db),
    auth=Depends(require_role([ClientRole.COORDINATOR, ClientRole.ENGINEER])),
):
    """
    Get list of available normalized tables for a scan.
    
    Requires COORDINATOR or ENGINEER role.
    """
    try:
        service = NormalizationService(db)
        tables = service.get_available_tables(scan_id)
        
        return {
            "scan_id": scan_id,
            "tables": tables,
        }
    
    except Exception as e:
        logger.error(f"Failed to get tables: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get tables: {str(e)}",
        )


@router.get("/supported-objects", response_model=SupportedObjectsResponse)
async def get_supported_objects(
    auth=Depends(require_role([ClientRole.COORDINATOR, ClientRole.ENGINEER])),
):
    """
    Get list of supported HubSpot object types.
    
    Requires COORDINATOR or ENGINEER role.
    """
    try:
        object_types = NormalizationService.get_supported_objects()
        
        return {
            "object_types": object_types,
        }
    
    except Exception as e:
        logger.error(f"Failed to get supported objects: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get supported objects: {str(e)}",
        )
