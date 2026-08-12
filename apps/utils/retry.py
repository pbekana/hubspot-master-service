"""Retry utilities for handling temporary failures."""
import asyncio
import random
import logging
from typing import Callable, TypeVar, Any, List
from functools import wraps
import httpx
from apps.config import settings

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RetryableError(Exception):
    """Base exception for retryable errors."""
    pass


class ExhaustedRetriesError(Exception):
    """Raised when all retry attempts have been exhausted."""
    pass


def is_retryable_error(exception: Exception) -> bool:
    """
    Check if an exception is retryable.
    
    Returns True for:
    - Connection errors
    - Timeouts
    - HTTP 500, 502, 503, 504
    
    Returns False for:
    - HTTP 429 (handled separately by rate limiter)
    - HTTP 4xx (client errors)
    - HTTP 200-299 (success)
    """
    if isinstance(exception, (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError)):
        return True
    
    if isinstance(exception, httpx.HTTPStatusError):
        status_code = exception.response.status_code
        # Retry on 5xx errors
        if status_code in [500, 502, 503, 504]:
            return True
        # Don't retry on 429 (handled by rate limiter)
        # Don't retry on other 4xx errors
        return False
    
    return False


async def retry_with_backoff(
    func: Callable[..., T],
    *args: Any,
    max_retries: int = None,
    delays: List[int] = None,
    jitter: float = None,
    **kwargs: Any
) -> T:
    """
    Retry a function with exponential backoff and jitter.
    
    Args:
        func: Async function to retry
        max_retries: Maximum number of retries
        delays: List of delay values in seconds
        jitter: Jitter factor (0-1) to add randomness
        *args, **kwargs: Arguments to pass to func
    
    Returns:
        Result from func
    
    Raises:
        ExhaustedRetriesError: If all retries are exhausted
    """
    if max_retries is None:
        max_retries = settings.external_call_max_retries
    if delays is None:
        delays = settings.retry_delays
    if jitter is None:
        jitter = settings.external_call_jitter
    
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            
            if not is_retryable_error(e):
                # Not a retryable error, raise immediately
                raise
            
            if attempt >= max_retries:
                # Exhausted all retries
                logger.error(f"Exhausted {max_retries} retries for {func.__name__}: {str(e)}")
                raise ExhaustedRetriesError(
                    f"Failed after {max_retries} retries: {str(e)}"
                ) from e
            
            # Calculate delay with jitter
            base_delay = delays[min(attempt, len(delays) - 1)]
            jitter_amount = base_delay * jitter * random.random()
            delay = base_delay + jitter_amount
            
            logger.warning(
                f"Retry {attempt + 1}/{max_retries} for {func.__name__} "
                f"after {delay:.2f}s: {str(e)}"
            )
            await asyncio.sleep(delay)
    
    # Should not reach here, but just in case
    raise ExhaustedRetriesError(
        f"Failed after {max_retries} retries: {str(last_exception)}"
    ) from last_exception


def with_retry(max_retries: int = None, delays: List[int] = None, jitter: float = None):
    """
    Decorator to add retry logic to async functions.
    
    Usage:
        @with_retry(max_retries=3)
        async def my_function():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await retry_with_backoff(
                func, *args,
                max_retries=max_retries,
                delays=delays,
                jitter=jitter,
                **kwargs
            )
        return wrapper
    return decorator
