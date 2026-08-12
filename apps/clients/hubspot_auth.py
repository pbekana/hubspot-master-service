"""HubSpot OAuth authentication client."""
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import httpx
from apps.config import settings
from apps.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class HubSpotAuthClient:
    """Client for HubSpot OAuth authentication."""
    
    def __init__(self):
        self.client_id = settings.hubspot_client_id
        self.client_secret = settings.hubspot_client_secret
        self.token_url = f"{settings.hubspot_api_base_url}/oauth/v1/token"
    
    async def get_access_token(
        self,
        refresh_token: Optional[str] = None,
        authorization_code: Optional[str] = None,
        redirect_uri: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get access token from HubSpot OAuth.
        
        Args:
            refresh_token: Refresh token for token refresh flow
            authorization_code: Authorization code for initial authorization flow
            redirect_uri: Redirect URI (required for authorization code flow)
        
        Returns:
            Dict with:
                - access_token: OAuth access token
                - refresh_token: OAuth refresh token
                - expires_in: Token expiry in seconds
                - expires_at: Token expiry datetime
        
        Raises:
            ValueError: If credentials are invalid
            httpx.HTTPStatusError: If OAuth request fails
        """
        if refresh_token:
            return await self._refresh_access_token(refresh_token)
        elif authorization_code and redirect_uri:
            return await self._exchange_authorization_code(authorization_code, redirect_uri)
        else:
            raise ValueError("Must provide either refresh_token or (authorization_code + redirect_uri)")
    
    async def _refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh access token using refresh token.
        
        Args:
            refresh_token: Refresh token
        
        Returns:
            Token response dict
        """
        logger.info("Refreshing HubSpot access token")
        
        async def _make_request():
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.token_url,
                    data={
                        "grant_type": "refresh_token",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "refresh_token": refresh_token,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=30.0,
                )
                response.raise_for_status()
                return response.json()
        
        token_data = await retry_with_backoff(_make_request)
        
        # Calculate expiry datetime
        expires_in = token_data.get("expires_in", 21600)  # Default 6 hours
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        
        token_data["expires_at"] = expires_at
        
        logger.info(f"Successfully refreshed access token, expires in {expires_in}s")
        return token_data
    
    async def _exchange_authorization_code(
        self,
        authorization_code: str,
        redirect_uri: str,
    ) -> Dict[str, Any]:
        """
        Exchange authorization code for access token.
        
        Args:
            authorization_code: Authorization code from OAuth redirect
            redirect_uri: Redirect URI used in authorization
        
        Returns:
            Token response dict
        """
        logger.info("Exchanging authorization code for access token")
        
        async def _make_request():
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.token_url,
                    data={
                        "grant_type": "authorization_code",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "redirect_uri": redirect_uri,
                        "code": authorization_code,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=30.0,
                )
                response.raise_for_status()
                return response.json()
        
        token_data = await retry_with_backoff(_make_request)
        
        # Calculate expiry datetime
        expires_in = token_data.get("expires_in", 21600)
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        
        token_data["expires_at"] = expires_at
        
        logger.info(f"Successfully obtained access token, expires in {expires_in}s")
        return token_data
    
    async def validate_credentials(
        self,
        access_token: str,
        refresh_token: Optional[str] = None,
    ) -> bool:
        """
        Validate HubSpot credentials by making a test API call.
        
        Args:
            access_token: Access token to validate
            refresh_token: Optional refresh token
        
        Returns:
            True if credentials are valid, False otherwise
        """
        try:
            # Try to fetch account info as validation
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{settings.hubspot_api_base_url}/oauth/v1/access-tokens/{access_token}",
                    timeout=10.0,
                )
                response.raise_for_status()
                logger.info("Credentials validated successfully")
                return True
        except Exception as e:
            logger.warning(f"Credential validation failed: {str(e)}")
            return False
