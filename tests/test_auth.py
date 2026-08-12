"""
Tests for HubSpot OAuth authentication.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
from apps.clients.hubspot_auth import HubSpotAuthClient


@pytest.fixture
def auth_client():
    """Create auth client."""
    return HubSpotAuthClient()


@pytest.mark.asyncio
async def test_refresh_access_token_success(auth_client):
    """Test successful token refresh."""
    mock_response_data = {
        "access_token": "new_access_token",
        "refresh_token": "new_refresh_token",
        "expires_in": 21600,
    }
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response
        
        # Test token refresh
        result = await auth_client.get_access_token(refresh_token="test_refresh_token")
        
        assert result["access_token"] == "new_access_token"
        assert result["refresh_token"] == "new_refresh_token"
        assert "expires_at" in result
        assert isinstance(result["expires_at"], datetime)


@pytest.mark.asyncio
async def test_exchange_authorization_code_success(auth_client):
    """Test successful authorization code exchange."""
    mock_response_data = {
        "access_token": "access_token_123",
        "refresh_token": "refresh_token_123",
        "expires_in": 21600,
    }
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response
        
        # Test authorization code exchange
        result = await auth_client.get_access_token(
            authorization_code="auth_code_123",
            redirect_uri="http://localhost:3000",
        )
        
        assert result["access_token"] == "access_token_123"
        assert result["refresh_token"] == "refresh_token_123"
        assert "expires_at" in result


@pytest.mark.asyncio
async def test_invalid_credentials_error(auth_client):
    """Test invalid credentials error handling."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Mock 401 unauthorized response
        from httpx import HTTPStatusError, Request, Response
        mock_response = Response(
            status_code=401,
            request=Request("POST", "https://api.hubapi.com/oauth/v1/token"),
        )
        mock_client.post.return_value = mock_response
        
        with pytest.raises(Exception):  # Should raise HTTPStatusError
            await auth_client.get_access_token(refresh_token="invalid_token")


@pytest.mark.asyncio
async def test_validate_credentials_valid(auth_client):
    """Test credential validation with valid token."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        
        result = await auth_client.validate_credentials("valid_token")
        
        assert result is True


@pytest.mark.asyncio
async def test_validate_credentials_invalid(auth_client):
    """Test credential validation with invalid token."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Mock 401 response
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status = MagicMock(side_effect=Exception("Unauthorized"))
        mock_client.get.return_value = mock_response
        
        result = await auth_client.validate_credentials("invalid_token")
        
        assert result is False


@pytest.mark.asyncio
async def test_get_access_token_missing_params(auth_client):
    """Test that missing parameters raise error."""
    with pytest.raises(ValueError, match="Must provide either"):
        await auth_client.get_access_token()


@pytest.mark.asyncio
async def test_exchange_authorization_code_failure(auth_client):
    """Test authorization code exchange failure handling."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        from httpx import Request, Response
        mock_response = Response(
            status_code=400,
            request=Request("POST", "https://api.hubapi.com/oauth/v1/token"),
        )
        mock_client.post.return_value = mock_response

        with pytest.raises(Exception):
            await auth_client.get_access_token(
                authorization_code="invalid_code",
                redirect_uri="http://localhost:3000",
            )


@pytest.mark.asyncio
async def test_refresh_access_token_expires_at_calculated(auth_client):
    """Test that refresh token expiry is computed correctly."""
    mock_response_data = {
        "access_token": "new_access_token",
        "refresh_token": "new_refresh_token",
        "expires_in": 10,
    }

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        result = await auth_client.get_access_token(refresh_token="test_refresh_token")

        assert result["expires_at"] > datetime.utcnow()
        assert result["expires_at"] <= datetime.utcnow() + timedelta(seconds=20)
