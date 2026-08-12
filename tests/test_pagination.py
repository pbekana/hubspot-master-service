"""
Tests for HubSpot API pagination.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from apps.clients.hubspot_api import HubSpotAPIClient


@pytest.fixture
def api_client():
    """Create API client with mock token."""
    return HubSpotAPIClient(access_token="test_token")


@pytest.mark.asyncio
async def test_get_first_page(api_client):
    """Test fetching the first page of results."""
    # Mock response
    mock_response = {
        "results": [
            {"id": "1", "properties": {"email": "test1@example.com"}},
            {"id": "2", "properties": {"email": "test2@example.com"}},
        ],
        "paging": {
            "next": {
                "after": "cursor_123"
            }
        }
    }
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_response_obj = MagicMock()
        mock_response_obj.status_code = 200
        mock_response_obj.json.return_value = mock_response
        mock_response_obj.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response_obj
        
        # Fetch first page
        result = await api_client.get_page("contacts")
        
        assert len(result["results"]) == 2
        assert result["paging"]["next"]["after"] == "cursor_123"
        assert result["results"][0]["id"] == "1"


@pytest.mark.asyncio
async def test_get_page_with_cursor(api_client):
    """Test fetching a page with cursor pagination."""
    mock_response = {
        "results": [
            {"id": "3", "properties": {"email": "test3@example.com"}},
        ],
        "paging": {
            "next": {
                "after": "cursor_456"
            }
        }
    }
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_response_obj = MagicMock()
        mock_response_obj.status_code = 200
        mock_response_obj.json.return_value = mock_response
        mock_response_obj.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response_obj
        
        # Fetch with cursor
        result = await api_client.get_page("contacts", after_cursor="cursor_123")
        
        assert len(result["results"]) == 1
        assert result["results"][0]["id"] == "3"


@pytest.mark.asyncio
async def test_get_last_page(api_client):
    """Test fetching the last page (no next cursor)."""
    mock_response = {
        "results": [
            {"id": "10", "properties": {"email": "test10@example.com"}},
        ],
        "paging": {}  # No next cursor
    }
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_response_obj = MagicMock()
        mock_response_obj.status_code = 200
        mock_response_obj.json.return_value = mock_response
        mock_response_obj.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response_obj
        
        # Fetch last page
        result = await api_client.get_page("contacts", after_cursor="cursor_999")
        
        assert len(result["results"]) == 1
        assert "next" not in result.get("paging", {})


@pytest.mark.asyncio
async def test_unsupported_object_type(api_client):
    """Test that unsupported object types raise error."""
    with pytest.raises(ValueError, match="Unsupported object type"):
        await api_client.get_page("invalid_type")


@pytest.mark.asyncio
async def test_page_size_limits(api_client):
    """Test that page size is capped at max limit."""
    mock_response = {
        "results": [],
        "paging": {}
    }
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_response_obj = MagicMock()
        mock_response_obj.status_code = 200
        mock_response_obj.json.return_value = mock_response
        mock_response_obj.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response_obj
        
        # Request page size larger than max
        await api_client.get_page("contacts", page_size=500)
        
        # Verify it was capped
        call_args = mock_client.get.call_args
        params = call_args.kwargs["params"]
        assert params["limit"] <= api_client.max_page_size
