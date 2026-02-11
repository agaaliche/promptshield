"""Remote LLM engine — calls OpenAI-compatible chat-completion APIs.

Supports any provider that exposes the ``/v1/chat/completions`` endpoint:
OpenAI, Anthropic (via proxy), Azure OpenAI, Groq, Together, Mistral,
local vLLM / Ollama servers, etc.

Only the ``httpx`` library is required (already a transitive dependency
of ``fastapi[standard]``).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import httpx

from core.config import config

logger = logging.getLogger(__name__)

# Defaults — can be overridden via configure().
_DEFAULT_REQUEST_TIMEOUT = 60.0
_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 1.5  # seconds — exponential backoff base


class RemoteLLMEngine:
    """
    OpenAI-compatible remote LLM wrapper.

    Uses a **persistent** ``httpx.Client`` for connection pooling and keep-alive.

    Usage:
        engine = RemoteLLMEngine()
        engine.configure("https://api.openai.com/v1", "sk-...", "gpt-4o-mini")
        response = engine.generate(system_prompt="...", user_prompt="...")
    """

    def __init__(self) -> None:
        self._api_url: str = ""
        self._api_key: str = ""
        self._model: str = ""
        self._timeout: float = _DEFAULT_REQUEST_TIMEOUT
        self._lock = threading.Lock()  # serialise for safety
        self._client: httpx.Client | None = None

    # ── Configuration ─────────────────────────────────────────────

    def configure(
        self,
        api_url: str,
        api_key: str,
        model: str,
        timeout: float = _DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
        """Set or update remote API parameters.

        Recreates the persistent HTTP client when the URL or key changes.
        """
        with self._lock:
            url_changed = api_url.rstrip("/") != self._api_url
            key_changed = api_key != self._api_key

            self._api_url = api_url.rstrip("/")
            self._api_key = api_key
            self._model = model
            self._timeout = timeout

            # Rebuild the pooled client when credentials change
            if url_changed or key_changed or self._client is None:
                if self._client is not None:
                    try:
                        self._client.close()
                    except Exception:
                        pass
                self._client = httpx.Client(
                    timeout=self._timeout,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                )

        logger.info(
            "Remote LLM configured: url=%s model=%s timeout=%ss",
            self._api_url, self._model, self._timeout,
        )

    def is_loaded(self) -> bool:
        """Return True when the remote engine is fully configured."""
        return bool(self._api_url and self._api_key and self._model)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def model_path(self) -> str:
        return self._api_url

    @property
    def gpu_enabled(self) -> bool:
        return False  # not applicable

    # ── Generation ────────────────────────────────────────────────

    def generate(
        self,
        system_prompt: str = "",
        user_prompt: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.7,
        top_p: float = 0.95,
        stop: Optional[list[str]] = None,
    ) -> str:
        """Call the remote chat-completion endpoint.

        The interface is identical to ``LLMEngine.generate`` so callers
        (``llm_detector.py``) work transparently with either backend.
        """
        if not self.is_loaded():
            raise RuntimeError(
                "Remote LLM not configured. Set API URL, key, and model first."
            )

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        payload: dict = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }
        if stop:
            payload["stop"] = stop

        url = f"{self._api_url}/chat/completions"

        with self._lock:
            return self._call(url, payload)

    def _call(self, url: str, payload: dict) -> str:
        """HTTP POST with retries and exponential backoff."""
        if self._client is None:
            raise RuntimeError("Remote LLM HTTP client not initialised — call configure() first")

        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = self._client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()

                # Standard OpenAI response shape
                text = data["choices"][0]["message"]["content"]
                return text.strip()

            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                body = e.response.text[:500] if e.response else ""
                # Retry on 429 (rate-limit) and 5xx (server errors)
                if status in (429, 500, 502, 503, 504) and attempt < _MAX_RETRIES - 1:
                    wait = _RETRY_BACKOFF_BASE ** attempt
                    logger.warning(
                        "Remote LLM HTTP %s (attempt %d/%d), retrying in %.1fs",
                        status, attempt + 1, _MAX_RETRIES, wait,
                    )
                    time.sleep(wait)
                    last_error = e
                    continue
                logger.error("Remote LLM HTTP %s: %s", status, body)
                raise RuntimeError(f"Remote LLM API error {status}: {body}") from e

            except httpx.TimeoutException as e:
                if attempt < _MAX_RETRIES - 1:
                    wait = _RETRY_BACKOFF_BASE ** attempt
                    logger.warning(
                        "Remote LLM timeout (attempt %d/%d), retrying in %.1fs",
                        attempt + 1, _MAX_RETRIES, wait,
                    )
                    time.sleep(wait)
                    last_error = e
                    continue
                logger.error("Remote LLM request timed out after %ss", self._timeout)
                raise RuntimeError("Remote LLM request timed out") from e

            except Exception as e:
                logger.error("Remote LLM request failed: %s", e)
                raise

        # Should not reach here, but just in case
        raise RuntimeError(f"Remote LLM request failed after {_MAX_RETRIES} retries") from last_error

    def test_connection(self) -> dict:
        """Quick connectivity check — sends a minimal request and reports latency."""
        import time

        if not self.is_loaded():
            return {"ok": False, "error": "Not configured"}

        t0 = time.perf_counter()
        try:
            resp_text = self.generate(
                system_prompt="Reply with exactly: OK",
                user_prompt="ping",
                max_tokens=4,
                temperature=0.0,
            )
            latency_ms = (time.perf_counter() - t0) * 1000
            return {
                "ok": True,
                "latency_ms": round(latency_ms),
                "model": self._model,
                "response": resp_text[:50],
            }
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000
            return {
                "ok": False,
                "latency_ms": round(latency_ms),
                "error": str(e)[:200],
            }


# Singleton
remote_llm_engine = RemoteLLMEngine()
