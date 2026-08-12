"""Dead Letter Queue utilities for storing failed external calls."""
import json
import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from apps.models.failed_external_call import FailedExternalCall
from apps.config import settings

logger = logging.getLogger(__name__)

# Sensitive field names to scrub from payloads
SENSITIVE_FIELDS = {
    "client_secret",
    "access_token",
    "refresh_token",
    "hmac_secret",
    "minio_secret",
    "password",
    "secret",
    "token",
    "key",
    "authorization",
}


def scrub_sensitive_data(payload: Any) -> Any:
    """
    Recursively scrub sensitive data from payload.
    
    Args:
        payload: Payload to scrub (dict, list, or primitive)
    
    Returns:
        Scrubbed payload
    """
    if isinstance(payload, dict):
        scrubbed = {}
        for key, value in payload.items():
            # Check if key is sensitive
            if any(sensitive in key.lower() for sensitive in SENSITIVE_FIELDS):
                scrubbed[key] = "[REDACTED]"
            else:
                scrubbed[key] = scrub_sensitive_data(value)
        return scrubbed
    elif isinstance(payload, list):
        return [scrub_sensitive_data(item) for item in payload]
    else:
        return payload


def write_to_dlq(
    db: Session,
    target_service: str,
    operation: str,
    payload: Optional[Dict[str, Any]],
    attempts: int,
    error: Exception,
    organization_id: Optional[str] = None,
    scan_id: Optional[int] = None,
) -> Optional[FailedExternalCall]:
    """
    Write a failed external call to the dead letter queue.
    
    Args:
        db: Database session
        target_service: Name of the external service
        operation: Operation that failed
        payload: Request payload (will be scrubbed)
        attempts: Number of attempts made
        error: Exception that caused the failure
        organization_id: Optional organization ID
        scan_id: Optional scan/job ID
    
    Returns:
        FailedExternalCall record or None if write failed
    """
    try:
        # Scrub sensitive data
        scrubbed_payload = scrub_sensitive_data(payload) if payload else None
        
        # Convert to JSON string and truncate if necessary
        payload_str = None
        if scrubbed_payload:
            payload_str = json.dumps(scrubbed_payload)
            if len(payload_str) > settings.dlq_payload_max_bytes:
                payload_str = payload_str[:settings.dlq_payload_max_bytes] + "...[truncated]"
        
        # Extract error details
        error_message = str(error)
        error_details = None
        if hasattr(error, "__dict__"):
            try:
                error_details = {
                    "type": type(error).__name__,
                    "args": error.args if hasattr(error, "args") else None,
                }
            except Exception:
                pass
        
        # Create DLQ record
        dlq_record = FailedExternalCall(
            target_service=target_service,
            operation=operation,
            payload=payload_str,
            attempts=attempts,
            error_message=error_message[:1000] if error_message else "Unknown error",
            error_details=error_details,
            organization_id=organization_id,
            scan_id=scan_id,
        )
        
        db.add(dlq_record)
        db.commit()
        
        logger.info(
            f"Wrote failed external call to DLQ: {target_service}.{operation} "
            f"after {attempts} attempts"
        )
        
        return dlq_record
        
    except Exception as dlq_error:
        # Don't let DLQ write failure break the main flow
        logger.error(f"Failed to write to DLQ: {str(dlq_error)}", exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass
        return None
