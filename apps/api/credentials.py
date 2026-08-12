"""
Credentials API router for validating HubSpot credentials.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from apps.clients.hubspot_auth import HubSpotAuthClient
from apps.api.schemas import ValidateCredentialsRequest, ValidateCredentialsResponse
from apps.utils.security import require_role, ClientRole

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/validate-credentials", response_model=ValidateCredentialsResponse)
async def validate_credentials(
    request: ValidateCredentialsRequest,
    auth=Depends(require_role([ClientRole.COORDINATOR, ClientRole.ENGINEER])),
):
    """
    Validate HubSpot OAuth credentials.
    
    Requires COORDINATOR or ENGINEER role.
    """
    try:
        auth_client = HubSpotAuthClient()
        
        # Validate credentials
        is_valid = await auth_client.validate_credentials(
            access_token=request.access_token,
            refresh_token=request.refresh_token,
        )
        
        if is_valid:
            logger.info("Credentials validated successfully")
            return {
                "valid": True,
                "message": "Credentials are valid",
                "token_info": None,
            }
        else:
            logger.warning("Credentials validation failed")
            return {
                "valid": False,
                "message": "Credentials are invalid or expired",
                "token_info": None,
            }
    
    except Exception as e:
        logger.error(f"Failed to validate credentials: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to validate credentials: {str(e)}",
        )
