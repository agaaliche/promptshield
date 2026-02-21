"""Extended integration tests for all API routers.

Uses httpx + ASGITransport to hit the FastAPI app without a real server.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.server import app
from api import deps

_HAS_SPACY = bool(sys.modules.get("spacy")) or True  # lazy imports, so check at call
_HAS_FITZ = bool(sys.modules.get("fitz")) or True

try:
    import spacy  # noqa: F401
    _HAS_SPACY = True
except ImportError:
    _HAS_SPACY = False

try:
    import fitz  # noqa: F401
    _HAS_FITZ = True
except ImportError:
    _HAS_FITZ = False


@pytest_asyncio.fixture
async def client():
    """Async HTTP client for testing FastAPI endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Requested-With": "XMLHttpRequest"},
    ) as ac:
        yield ac


# ───────────────────────── Health ─────────────────────────

class TestHealth:
    @pytest.mark.asyncio
    async def test_health(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ───────────────────────── Documents ─────────────────────────

class TestDocuments:
    @pytest.mark.asyncio
    async def test_list_empty(self, client: AsyncClient):
        resp = await client.get("/api/documents")
        assert resp.status_code == 200
        data = resp.json()
        # Paginated response by default
        assert "items" in data
        assert isinstance(data["items"], list)
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_empty_flat(self, client: AsyncClient):
        """Test that paginated=false returns a flat list."""
        resp = await client.get("/api/documents?paginated=false")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_get_missing(self, client: AsyncClient):
        resp = await client.get("/api/documents/no-such-id")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_missing(self, client: AsyncClient):
        resp = await client.delete("/api/documents/no-such-id")
        assert resp.status_code == 404


# ───────────────────────── Settings ─────────────────────────

class TestSettings:
    @pytest.mark.asyncio
    async def test_get_settings(self, client: AsyncClient):
        resp = await client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert "confidence_threshold" in data

    @pytest.mark.asyncio
    async def test_patch_settings_allowed(self, client: AsyncClient):
        resp = await client.patch(
            "/api/settings",
            json={"confidence_threshold": 0.42},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["applied"]["confidence_threshold"] == 0.42

    @pytest.mark.asyncio
    async def test_patch_settings_unknown_key_ignored(self, client: AsyncClient):
        resp = await client.patch(
            "/api/settings",
            json={"nonexistent_key": True},
        )
        assert resp.status_code == 200
        assert resp.json()["applied"] == {}

    @pytest.mark.asyncio
    async def test_get_labels(self, client: AsyncClient):
        # get_store() requires a real DocumentStore — provide a mock
        mock_store = MagicMock()
        mock_store.load_label_config.return_value = []
        old_store = deps.store
        deps.store = mock_store
        try:
            resp = await client.get("/api/settings/labels")
        finally:
            deps.store = old_store
        assert resp.status_code == 200
        labels = resp.json()
        assert isinstance(labels, list)
        names = {l["label"] for l in labels}
        assert "PERSON" in names
        assert "EMAIL" in names


# ───────────────────────── Vault ─────────────────────────

class TestVault:
    @pytest.mark.asyncio
    async def test_vault_status(self, client: AsyncClient):
        resp = await client.get("/api/vault/status")
        assert resp.status_code == 200
        assert "unlocked" in resp.json()

    @pytest.mark.asyncio
    async def test_vault_stats_returns_ok(self, client: AsyncClient):
        """Vault auto-initialises — stats are always accessible."""
        resp = await client.get("/api/vault/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_tokens" in data

    @pytest.mark.asyncio
    async def test_vault_tokens_returns_ok(self, client: AsyncClient):
        """Vault auto-initialises — token list is always accessible."""
        resp = await client.get("/api/vault/tokens")
        assert resp.status_code == 200
        data = resp.json()
        assert "tokens" in data
        assert "total" in data


# ───────────────────────── LLM ─────────────────────────

class TestLLM:
    @pytest.mark.asyncio
    async def test_llm_status(self, client: AsyncClient):
        resp = await client.get("/api/llm/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "loaded" in data
        assert "provider" in data

    @pytest.mark.asyncio
    async def test_list_models(self, client: AsyncClient):
        resp = await client.get("/api/llm/models")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_set_invalid_provider(self, client: AsyncClient):
        resp = await client.post("/api/llm/provider", params={"provider": "invalid"})
        assert resp.status_code == 400


# ───────────────────────── Detokenize ─────────────────────────

class TestDetokenize:
    @pytest.mark.asyncio
    async def test_detokenize_no_tokens(self, client: AsyncClient):
        mock_vault = type("MockVault", (), {
            "is_unlocked": True,
            "ensure_ready": lambda self: None,
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


# ───────────────────────── Detection ─────────────────────────

class TestDetection:
    @pytest.mark.asyncio
    async def test_detection_progress_idle(self, client: AsyncClient):
        """Progress for an unknwn doc should return idle."""
        resp = await client.get("/api/documents/no-doc/detection-progress")
        assert resp.status_code == 200
        assert resp.json()["status"] == "idle"

    @pytest.mark.asyncio
    async def test_detect_missing_doc(self, client: AsyncClient):
        resp = await client.post("/api/documents/no-doc/detect")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_redetect_missing_doc(self, client: AsyncClient):
        resp = await client.post(
            "/api/documents/no-doc/redetect",
            json={"confidence_threshold": 0.5},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_reset_detection_missing_doc(self, client: AsyncClient):
        resp = await client.post("/api/documents/no-doc/reset-detection")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_regions_missing_doc(self, client: AsyncClient):
        resp = await client.get("/api/documents/no-doc/regions")
        assert resp.status_code == 404


# ───────────────────────── Regions ─────────────────────────

class TestRegions:
    @pytest.mark.asyncio
    async def test_set_action_missing_doc(self, client: AsyncClient):
        resp = await client.put(
            "/api/documents/no-doc/regions/r1/action",
            json={"region_id": "r1", "action": "TOKENIZE"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_region_missing_doc(self, client: AsyncClient):
        resp = await client.delete("/api/documents/no-doc/regions/r1")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_debug_detections_missing(self, client: AsyncClient):
        resp = await client.get("/api/documents/no-doc/debug-detections")
        assert resp.status_code == 404


# ───────────────────────── Anonymize ─────────────────────────

class TestAnonymize:
    @pytest.mark.asyncio
    async def test_anonymize_missing_doc(self, client: AsyncClient):
        resp = await client.post("/api/documents/no-doc/anonymize")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_download_missing_doc(self, client: AsyncClient):
        resp = await client.get("/api/documents/no-doc/download/pdf")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_batch_anonymize_empty(self, client: AsyncClient):
        resp = await client.post(
            "/api/documents/batch-anonymize",
            json={"doc_ids": []},
        )
        assert resp.status_code == 400
