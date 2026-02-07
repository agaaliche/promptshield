"""Tests for the FastAPI server endpoints."""

from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from api.server import app


@pytest_asyncio.fixture
async def client():
    """Async HTTP client for testing FastAPI endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data


class TestDocumentEndpoints:
    @pytest.mark.asyncio
    async def test_list_documents_empty(self, client: AsyncClient):
        resp = await client.get("/api/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_nonexistent_document(self, client: AsyncClient):
        resp = await client.get("/api/documents/nonexistent-id")
        assert resp.status_code == 404


class TestVaultEndpoints:
    @pytest.mark.asyncio
    async def test_vault_status(self, client: AsyncClient):
        resp = await client.get("/api/vault/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "unlocked" in data


class TestLLMEndpoints:
    @pytest.mark.asyncio
    async def test_llm_status(self, client: AsyncClient):
        resp = await client.get("/api/llm/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "loaded" in data

    @pytest.mark.asyncio
    async def test_list_models(self, client: AsyncClient):
        resp = await client.get("/api/llm/models")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


class TestDetokenizeEndpoint:
    @pytest.mark.asyncio
    async def test_detokenize_no_tokens(self, client: AsyncClient):
        mock_vault = type("MockVault", (), {
            "is_unlocked": True,
            "resolve_all_tokens": lambda self, text: (text, 0, []),
        })()
        with patch("core.vault.store.vault", mock_vault):
            resp = await client.post(
                "/api/detokenize",
                json={"text": "Hello world, no tokens here."},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tokens_replaced"] == 0
        assert data["original_text"] == "Hello world, no tokens here."
