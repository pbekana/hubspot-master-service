import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock
from apps.utils.retry import (
    is_retryable_error,
    retry_with_backoff,
    ExhaustedRetriesError,
)
from apps.utils.rate_limiter import RateLimiter
from apps.config import settings


@pytest.mark.asyncio
async def test_is_retryable_error_timeout():
    assert is_retryable_error(httpx.TimeoutException("timeout")) is True


@pytest.mark.asyncio
async def test_is_retryable_error_http_5xx():
    request = httpx.Request("GET", "https://example.com")
    response = httpx.Response(500, request=request)
    err = httpx.HTTPStatusError("Internal", request=request, response=response)
    assert is_retryable_error(err) is True


@pytest.mark.asyncio
async def test_is_retryable_error_http_429():
    request = httpx.Request("GET", "https://example.com")
    response = httpx.Response(429, request=request)
    err = httpx.HTTPStatusError("Too Many Requests", request=request, response=response)
    assert is_retryable_error(err) is False


@pytest.mark.asyncio
async def test_retry_success_after_transient_error(monkeypatch):
    monkeypatch.setattr(settings, "external_call_max_retries", 2)
    monkeypatch.setattr(settings, "external_call_retry_delays", "0")
    monkeypatch.setattr(settings, "external_call_jitter", 0.0)

    attempts = {"count": 0}

    async def flaky():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx.ConnectError("connection failed")
        return "ok"

    result = await retry_with_backoff(flaky)
    assert result == "ok"
    assert attempts["count"] == 2


@pytest.mark.asyncio
async def test_retry_exhaustion(monkeypatch):
    monkeypatch.setattr(settings, "external_call_max_retries", 1)
    monkeypatch.setattr(settings, "external_call_retry_delays", "0")
    monkeypatch.setattr(settings, "external_call_jitter", 0.0)

    async def fail_always():
        raise httpx.ConnectError("connection lost")

    with pytest.raises(ExhaustedRetriesError):
        await retry_with_backoff(fail_always)


@pytest.mark.asyncio
async def test_retry_does_not_retry_429(monkeypatch):
    monkeypatch.setattr(settings, "external_call_max_retries", 2)
    monkeypatch.setattr(settings, "external_call_retry_delays", "0")
    monkeypatch.setattr(settings, "external_call_jitter", 0.0)

    request = httpx.Request("GET", "https://example.com")
    response = httpx.Response(429, request=request)
    err = httpx.HTTPStatusError("Too Many Requests", request=request, response=response)

    async def raise_429():
        raise err

    with pytest.raises(httpx.HTTPStatusError):
        await retry_with_backoff(raise_429)


@pytest.mark.asyncio
async def test_rate_limiter_wait_if_needed(monkeypatch):
    limiter = RateLimiter()
    limiter.burst_limit = 1
    limiter.window_seconds = 10
    limiter.request_times = [100.0]

    times = [100.0]

    def fake_time():
        return times[0]

    monkeypatch.setattr("apps.utils.rate_limiter.time.time", fake_time)
    called = {"slept": None}

    async def fake_sleep(delay):
        called["slept"] = delay

    monkeypatch.setattr("apps.utils.rate_limiter.asyncio.sleep", fake_sleep)

    await limiter.wait_if_needed()
    assert called["slept"] == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_rate_limiter_handle_429_with_retry_after(monkeypatch):
    limiter = RateLimiter()
    called = {"delay": None}

    async def fake_sleep(delay):
        called["delay"] = delay

    monkeypatch.setattr("apps.utils.rate_limiter.asyncio.sleep", fake_sleep)
    await limiter.handle_429(7)

    assert called["delay"] == 7


@pytest.mark.asyncio
async def test_rate_limiter_handle_429_without_retry_after(monkeypatch):
    limiter = RateLimiter()
    called = {"delay": None}

    async def fake_sleep(delay):
        called["delay"] = delay

    monkeypatch.setattr("apps.utils.rate_limiter.asyncio.sleep", fake_sleep)
    await limiter.handle_429(None)

    assert called["delay"] == limiter.default_retry_after
