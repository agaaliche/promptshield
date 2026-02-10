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
from typing import Optional

import httpx

from core.config import config

logger = logging.getLogger(__name__)

# Timeout for a single chat-completion request (seconds).
_REQUEST_TIMEOUT = 60.0


class RemoteLLMEngine:
    """
    OpenAI-compatible remote LLM wrapper.

    Usage:
        engine = RemoteLLMEngine()
        engine.configure("https://api.openai.com/v1", "sk-...", "gpt-4o-mini")
        response = engine.generate(system_prompt="...", user_prompt="...")
    """

    def __init__(self) -> None:
        self._api_url: str = ""
        self._api_key: str = ""
        self._model: str = ""
        self._lock = threading.Lock()  # serialise for safety

    # ── Configuration ─────────────────────────────────────────────

    def configure(
        self,
        api_url: str,
        api_key: str,
        model: str,
    ) -> None:
        """Set or update remote API parameters."""
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        logger.info(
            "Remote LLM configured: url=%s model=%s",
            self._api_url, self._model,
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

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self._api_url}/chat/completions"

        with self._lock:
            return self._call(url, headers, payload)

    def _call(self, url: str, headers: dict, payload: dict) -> str:
        """HTTP POST with retries."""
        try:
            with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            # Standard OpenAI response shape
            text = data["choices"][0]["message"]["content"]
            return text.strip()

        except httpx.HTTPStatusError as e:
            body = e.response.text[:500] if e.response else ""
            logger.error("Remote LLM HTTP %s: %s", e.response.status_code, body)
            raise RuntimeError(f"Remote LLM API error {e.response.status_code}: {body}") from e
        except httpx.TimeoutException:
            logger.error("Remote LLM request timed out after %ss", _REQUEST_TIMEOUT)
            raise RuntimeError("Remote LLM request timed out")
        except Exception as e:
            logger.error("Remote LLM request failed: %s", e)
            raise

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
