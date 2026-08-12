"""Security utilities for HMAC authentication."""
import hashlib
import hmac
import time
import logging
from typing import Optional, Tuple
from fastapi import HTTPException, Request
from apps.config import settings

logger = logging.getLogger(__name__)


class ClientRole:
    """Client roles for authorization."""
    COORDINATOR = "coordinator"  # Full access
    ENGINEER = "engineer"  # Read-only access


# Map client IDs to their secrets and roles
CLIENT_CONFIGS = {}


def init_hmac_clients():
    """Initialize HMAC client configurations."""
    global CLIENT_CONFIGS
    
    if settings.hmac_secret_key_core:
        CLIENT_CONFIGS["coordinator"] = {
            "secret": settings.hmac_secret_key_core,
            "role": ClientRole.COORDINATOR,
        }
    
    if settings.hmac_secret_key_engineer:
        CLIENT_CONFIGS["engineer"] = {
            "secret": settings.hmac_secret_key_engineer,
            "role": ClientRole.ENGINEER,
        }


def compute_signature(
    method: str,
    path: str,
    timestamp: str,
    nonce: str,
    body_hash: str,
    secret: str,
) -> str:
    """
    Compute HMAC-SHA256 signature.
    
    Canonical string format:
    METHOD\nPATH\nTIMESTAMP\nNONCE\nBODY_HASH
    
    Args:
        method: HTTP method
        path: Request path
        timestamp: Unix timestamp as string
        nonce: Random nonce
        body_hash: SHA256 hash of request body
        secret: HMAC secret key
    
    Returns:
        Hex-encoded HMAC signature
    """
    canonical_string = f"{method}\n{path}\n{timestamp}\n{nonce}\n{body_hash}"
    signature = hmac.new(
        secret.encode("utf-8"),
        canonical_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return signature


def hash_body(body: bytes) -> str:
    """Compute SHA256 hash of request body."""
    return hashlib.sha256(body).hexdigest()


async def verify_hmac_signature(request: Request) -> Tuple[str, str]:
    """
    Verify HMAC signature from request headers.
    
    Args:
        request: FastAPI request
    
    Returns:
        Tuple of (client_id, client_role)
    
    Raises:
        HTTPException: If authentication fails
    """
    if not settings.hmac_enabled:
        # HMAC disabled, allow request (for development)
        logger.warning("HMAC authentication is disabled")
        return "anonymous", ClientRole.COORDINATOR
    
    # Initialize clients if not done yet
    if not CLIENT_CONFIGS:
        init_hmac_clients()
    
    # Extract headers
    signature = request.headers.get("X-HS-Signature")
    timestamp = request.headers.get("X-HS-Timestamp")
    client_id = request.headers.get("X-HS-Client-ID")
    nonce = request.headers.get("X-HS-Nonce")
    
    if not all([signature, timestamp, client_id, nonce]):
        logger.warning("Missing HMAC authentication headers")
        raise HTTPException(
            status_code=401,
            detail="Missing authentication headers",
        )
    
    # Verify client exists
    client_config = CLIENT_CONFIGS.get(client_id)
    if not client_config:
        logger.warning(f"Unknown client ID: {client_id}")
        raise HTTPException(
            status_code=401,
            detail="Invalid client ID",
        )
    
    # Verify timestamp freshness
    try:
        request_time = int(timestamp)
        current_time = int(time.time())
        age = abs(current_time - request_time)
        
        if age > settings.hmac_signature_max_age:
            logger.warning(f"Signature too old: {age} seconds")
            raise HTTPException(
                status_code=401,
                detail="Signature expired",
            )
    except ValueError:
        logger.warning(f"Invalid timestamp format: {timestamp}")
        raise HTTPException(
            status_code=401,
            detail="Invalid timestamp",
        )
    
    # Compute body hash
    body = await request.body()
    body_hash = hash_body(body)
    
    # Compute expected signature
    expected_signature = compute_signature(
        method=request.method,
        path=request.url.path,
        timestamp=timestamp,
        nonce=nonce,
        body_hash=body_hash,
        secret=client_config["secret"],
    )
    
    # Verify signature
    if not hmac.compare_digest(signature, expected_signature):
        logger.warning(f"Invalid signature for client: {client_id}")
        raise HTTPException(
            status_code=401,
            detail="Invalid signature",
        )
    
    # TODO: Implement nonce replay protection (store used nonces in cache/db)
    
    logger.info(f"Authenticated request from client: {client_id}")
    return client_id, client_config["role"]


def require_role(allowed_roles: list):
    """
    Dependency to check if client has required role.
    
    Usage:
        @router.get("/endpoint", dependencies=[Depends(require_role([ClientRole.COORDINATOR]))])
    """
    async def check_role(request: Request):
        client_id, client_role = await verify_hmac_signature(request)
        
        if client_role not in allowed_roles:
            logger.warning(f"Client {client_id} with role {client_role} not authorized")
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions",
            )
        
        return client_id, client_role
    
    return check_role
