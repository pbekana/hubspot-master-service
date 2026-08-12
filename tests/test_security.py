import time
import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import Request
from starlette.types import Receive, Scope
from apps.utils.security import (
    compute_signature,
    hash_body,
    init_hmac_clients,
    CLIENT_CONFIGS,
    verify_hmac_signature,
    ClientRole,
)


def build_request(method: str, path: str, body: bytes, headers: dict) -> Request:
    # Build proper headers list for starlette
    header_list = []
    for k, v in headers.items():
        header_list.append((k.lower().encode("latin-1"), v.encode("latin-1")))
    
    scope: Scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": header_list,
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
        "scheme": "http",
        "http_version": "1.1",
        "root_path": "",
        "asgi": {"version": "3.0"},
    }

    async def receive() -> Receive:
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(scope, receive)
    # Mock the body() method to return our body
    request.body = AsyncMock(return_value=body)
    return request


def test_compute_signature_matches_expected():
    method = "POST"
    path = "/api/scan/start"
    timestamp = "1700000000"
    nonce = "nonce123"
    body = b"{\"name\":\"test\"}"
    secret = "test-secret"

    body_hash = hash_body(body)
    signature = compute_signature(method, path, timestamp, nonce, body_hash, secret)

    expected = compute_signature(method, path, timestamp, nonce, body_hash, secret)
    assert signature == expected


@pytest.mark.asyncio
async def test_verify_hmac_signature_valid():
    init_hmac_clients()
    secret = CLIENT_CONFIGS["coordinator"]["secret"]
    method = "GET"
    path = "/api/health"
    timestamp = str(int(time.time()))
    nonce = "nonce-valid"
    body = b""
    body_hash = hash_body(body)
    signature = compute_signature(method, path, timestamp, nonce, body_hash, secret)

    request = build_request(
        method,
        path,
        body,
        {
            "X-HS-Client-ID": "coordinator",
            "X-HS-Timestamp": timestamp,
            "X-HS-Nonce": nonce,
            "X-HS-Signature": signature,
        },
    )

    client_id, role = await verify_hmac_signature(request)
    assert client_id == "coordinator"
    assert role == ClientRole.COORDINATOR


@pytest.mark.asyncio
async def test_verify_hmac_signature_invalid_signature():
    init_hmac_clients()
    request = build_request(
        "GET",
        "/api/health",
        b"",
        {
            "X-HS-Client-ID": "coordinator",
            "X-HS-Timestamp": str(int(time.time())),
            "X-HS-Nonce": "nonce-invalid",
            "X-HS-Signature": "invalid-signature",
        },
    )

    with pytest.raises(Exception) as exc:
        await verify_hmac_signature(request)

    assert "Invalid signature" in str(exc.value)


@pytest.mark.asyncio
async def test_verify_hmac_signature_missing_headers():
    request = build_request("GET", "/api/health", b"", {})

    with pytest.raises(Exception) as exc:
        await verify_hmac_signature(request)

    assert "Missing authentication headers" in str(exc.value)


@pytest.mark.asyncio
async def test_verify_hmac_signature_expired_timestamp(monkeypatch):
    init_hmac_clients()
    secret = CLIENT_CONFIGS["coordinator"]["secret"]
    method = "GET"
    path = "/api/health"
    timestamp = str(int(time.time()) - 1000)
    nonce = "nonce-expired"
    body = b""
    body_hash = hash_body(body)
    signature = compute_signature(method, path, timestamp, nonce, body_hash, secret)

    request = build_request(
        method,
        path,
        body,
        {
            "X-HS-Client-ID": "coordinator",
            "X-HS-Timestamp": timestamp,
            "X-HS-Nonce": nonce,
            "X-HS-Signature": signature,
        },
    )

    with pytest.raises(Exception) as exc:
        await verify_hmac_signature(request)

    assert "Signature expired" in str(exc.value)
