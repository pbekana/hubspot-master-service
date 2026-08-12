"""Rate limiting utilities for HubSpot API calls."""
import asyncio
import time
import logging
from typing import Optional
from apps.config import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Rate limiter for HubSpot API calls.
    Handles HTTP 429 responses with Retry-After header.
    """
    
    def __init__(self):
        self.burst_limit = settings.hubspot_burst_limit
        self.window_seconds = settings.hubspot_rate_limit_window_seconds
        self.default_retry_after = settings.hubspot_default_retry_after
        self.request_times = []
    
    async def wait_if_needed(self):
        """Wait if we're approaching rate limits."""
        current_time = time.time()
        
        # Remove requests outside the current window
        self.request_times = [
            t for t in self.request_times
            if current_time - t < self.window_seconds
        ]
        
        # Check if we need to wait
        if len(self.request_times) >= self.burst_limit:
            oldest_request = self.request_times[0]
            wait_time = self.window_seconds - (current_time - oldest_request)
            if wait_time > 0:
                logger.warning(f"Rate limit approaching, waiting {wait_time:.2f} seconds")
                await asyncio.sleep(wait_time)
                # Clean up after waiting
                current_time = time.time()
                self.request_times = [
                    t for t in self.request_times
                    if current_time - t < self.window_seconds
                ]
        
        # Record this request
        self.request_times.append(current_time)
    
    async def handle_429(self, retry_after: Optional[int] = None):
        """
        Handle HTTP 429 response.
        
        Args:
            retry_after: Value from Retry-After header in seconds
        """
        wait_time = retry_after if retry_after is not None else self.default_retry_after
        logger.warning(f"Received 429 rate limit, waiting {wait_time} seconds")
        await asyncio.sleep(wait_time)
        # Clear request history after being rate limited
        self.request_times = []


# Global rate limiter instance
rate_limiter = RateLimiter()
