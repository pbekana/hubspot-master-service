"""HubSpot API client for CRM data extraction."""
import logging
from typing import Dict, Any, List, Optional
import httpx
from apps.config import settings
from apps.utils.rate_limiter import rate_limiter
from apps.utils.retry import retry_with_backoff, ExhaustedRetriesError

logger = logging.getLogger(__name__)


class HubSpotAPIClient:
    """Client for HubSpot CRM API."""
    
    # Supported object types
    SUPPORTED_OBJECTS = [
        "contacts",
        "companies",
        "deals",
        "tickets",
        "owners",
    ]
    
    def __init__(self, access_token: str):
        """
        Initialize HubSpot API client.
        
        Args:
            access_token: OAuth access token
        """
        self.access_token = access_token
        self.base_url = settings.hubspot_api_base_url
        self.api_version = settings.hubspot_api_version
        self.default_page_size = settings.hubspot_default_page_size
        self.max_page_size = settings.hubspot_max_page_size
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authorization."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
    
    async def get_page(
        self,
        object_type: str,
        after_cursor: Optional[str] = None,
        page_size: Optional[int] = None,
        properties: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Get a page of records for a specific object type.
        
        Args:
            object_type: HubSpot object type (contacts, companies, etc.)
            after_cursor: Pagination cursor from previous page
            page_size: Number of records per page
            properties: List of properties to fetch (fetches all if None)
        
        Returns:
            Dict with:
                - results: List of records
                - paging: Pagination info with 'next' cursor if more pages exist
        
        Raises:
            ValueError: If object_type is not supported
            httpx.HTTPStatusError: If API request fails
            ExhaustedRetriesError: If all retries are exhausted
        """
        if object_type not in self.SUPPORTED_OBJECTS:
            raise ValueError(f"Unsupported object type: {object_type}. Must be one of {self.SUPPORTED_OBJECTS}")
        
        if page_size is None:
            page_size = self.default_page_size
        elif page_size > self.max_page_size:
            page_size = self.max_page_size
        
        # Build URL
        url = f"{self.base_url}/crm/{self.api_version}/objects/{object_type}"
        
        # Build query parameters
        params = {
            "limit": page_size,
        }
        if after_cursor:
            params["after"] = after_cursor
        if properties:
            params["properties"] = ",".join(properties)
        
        logger.info(f"Fetching page of {object_type} (cursor={after_cursor}, limit={page_size})")
        
        # Make request with rate limiting and retry
        async def _make_request():
            # Wait if rate limit approached
            await rate_limiter.wait_if_needed()
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    params=params,
                    headers=self._get_headers(),
                    timeout=30.0,
                )
                
                # Handle 429 rate limit
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    retry_after_int = int(retry_after) if retry_after else None
                    await rate_limiter.handle_429(retry_after_int)
                    # Retry the same request after waiting
                    return await _make_request()
                
                response.raise_for_status()
                return response.json()
        
        try:
            data = await retry_with_backoff(_make_request)
            logger.info(f"Fetched {len(data.get('results', []))} {object_type}")
            return data
        except ExhaustedRetriesError as e:
            logger.error(f"Failed to fetch {object_type} page after retries: {str(e)}")
            raise
    
    async def get_associations(
        self,
        object_type: str,
        record_id: str,
        to_object_type: str,
    ) -> List[Dict[str, Any]]:
        """
        Get associations for a specific record.
        
        Args:
            object_type: Source object type
            record_id: Record ID
            to_object_type: Target object type
        
        Returns:
            List of associated records
        
        Raises:
            httpx.HTTPStatusError: If API request fails
        """
        url = f"{self.base_url}/crm/{self.api_version}/objects/{object_type}/{record_id}/associations/{to_object_type}"
        
        logger.debug(f"Fetching associations: {object_type}/{record_id} -> {to_object_type}")
        
        async def _make_request():
            await rate_limiter.wait_if_needed()
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers=self._get_headers(),
                    timeout=30.0,
                )
                
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    retry_after_int = int(retry_after) if retry_after else None
                    await rate_limiter.handle_429(retry_after_int)
                    return await _make_request()
                
                # 404 means no associations, return empty list
                if response.status_code == 404:
                    return {"results": []}
                
                response.raise_for_status()
                return response.json()
        
        try:
            data = await retry_with_backoff(_make_request)
            results = data.get("results", [])
            logger.debug(f"Found {len(results)} associations")
            return results
        except ExhaustedRetriesError as e:
            logger.error(f"Failed to fetch associations after retries: {str(e)}")
            raise
    
    async def get_all_pages(
        self,
        object_type: str,
        page_size: Optional[int] = None,
        properties: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get all records for an object type by paginating through all pages.
        
        WARNING: This loads all records into memory. Use with caution for large datasets.
        Prefer processing page-by-page in production.
        
        Args:
            object_type: HubSpot object type
            page_size: Number of records per page
            properties: List of properties to fetch
        
        Returns:
            List of all records
        """
        all_records = []
        after_cursor = None
        
        while True:
            page_data = await self.get_page(
                object_type=object_type,
                after_cursor=after_cursor,
                page_size=page_size,
                properties=properties,
            )
            
            records = page_data.get("results", [])
            all_records.extend(records)
            
            # Check for next page
            paging = page_data.get("paging", {})
            next_cursor = paging.get("next", {}).get("after")
            
            if not next_cursor:
                break
            
            after_cursor = next_cursor
        
        logger.info(f"Fetched total of {len(all_records)} {object_type}")
        return all_records
