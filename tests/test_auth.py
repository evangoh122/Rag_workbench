import os
import pytest
from fastapi import Request, HTTPException
from unittest.mock import MagicMock, patch
from api.middleware.auth import (
    get_read_api_key, get_write_api_key, get_admin_api_key
)

class TestAuthMiddleware:
    @pytest.fixture
    def mock_request(self):
        def _make_request(api_key: str | None = None):
            request = MagicMock(spec=Request)
            request.headers = {"X-API-Key": api_key} if api_key else {}
            return request
        return _make_request

    @pytest.fixture(autouse=True)
    def setup_keys(self):
        keys = {
            "READ_API_KEY": "read-123",
            "WRITE_API_KEY": "write-123",
            "ADMIN_API_KEY": "admin-123"
        }
        with patch.dict(os.environ, keys):
            yield

    @pytest.mark.asyncio
    async def test_get_read_api_key_success(self, mock_request):
        # Admin key should work for Read
        req = mock_request("admin-123")
        assert await get_read_api_key(req) == "admin-123"
        
        # Write key should work for Read
        req = mock_request("write-123")
        assert await get_read_api_key(req) == "write-123"
        
        # Read key should work for Read
        req = mock_request("read-123")
        assert await get_read_api_key(req) == "read-123"

    @pytest.mark.asyncio
    async def test_get_read_api_key_failure(self, mock_request):
        req = mock_request("wrong-key")
        with pytest.raises(HTTPException) as exc:
            await get_read_api_key(req)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_get_write_api_key_hierarchy(self, mock_request):
        # Admin key should work for Write
        req = mock_request("admin-123")
        assert await get_write_api_key(req) == "admin-123"
        
        # Write key should work for Write
        req = mock_request("write-123")
        assert await get_write_api_key(req) == "write-123"
        
        # Read key should NOT work for Write
        req = mock_request("read-123")
        with pytest.raises(HTTPException) as exc:
            await get_write_api_key(req)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_get_admin_api_key_strict(self, mock_request):
        # Admin key should work
        req = mock_request("admin-123")
        assert await get_admin_api_key(req) == "admin-123"
        
        # Write key should NOT work
        req = mock_request("write-123")
        with pytest.raises(HTTPException) as exc:
            await get_admin_api_key(req)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_missing_header(self, mock_request):
        req = mock_request(None)
        with pytest.raises(HTTPException) as exc:
            await get_read_api_key(req)
        assert exc.value.status_code == 401
        assert "header required" in exc.value.detail

    @pytest.mark.asyncio
    async def test_empty_header(self, mock_request):
        req = mock_request("")
        with pytest.raises(HTTPException) as exc:
            await get_read_api_key(req)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_no_keys_configured(self, mock_request):
        with patch.dict(os.environ, {}, clear=True):
            req = mock_request("any-key")
            with pytest.raises(HTTPException) as exc:
                await get_read_api_key(req)
            assert exc.value.status_code == 503
            assert "Service not configured" in exc.value.detail

    @pytest.mark.asyncio
    async def test_fallback_to_base_api_key(self, mock_request):
        with patch.dict(os.environ, {"API_KEY": "base-secret"}, clear=True):
            req = mock_request("base-secret")
            assert await get_read_api_key(req) == "base-secret"
            
            # Should also work for write if no specific write key is set
            assert await get_write_api_key(req) == "base-secret"
