"""Embedded LLM engine — manages llama-cpp-python for local inference."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from core.config import config

logger = logging.getLogger(__name__)


class LLMEngine:
    """
    Wraps llama-cpp-python to provide local LLM inference.

    Usage:
        engine = LLMEngine()
        engine.load_model("/path/to/model.gguf")
        response = engine.generate(system_prompt="...", user_prompt="...")
    """

    def __init__(self):
        self._llm = None
        self._model_path: str = ""
        self._model_name: str = ""
        self._gpu_enabled: bool = False

    def is_loaded(self) -> bool:
        return self._llm is not None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_path(self) -> str:
        return self._model_path

    @property
    def gpu_enabled(self) -> bool:
        return self._gpu_enabled

    def load_model(self, model_path: str, force_cpu: bool = False) -> None:
        """
        Load a GGUF model file.

        Args:
            model_path: Absolute path to the .gguf model file.
            force_cpu: If True, disable GPU even if available.
        """
        from llama_cpp import Llama

        path = Path(model_path)
        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        if not path.suffix.lower() == ".gguf":
            raise ValueError(f"Expected a .gguf model file, got: {path.suffix}")

        # Determine thread count
        n_threads = config.llm_threads
        if n_threads <= 0:
            n_threads = max(1, os.cpu_count() or 4)

        # Determine GPU layers
        n_gpu_layers = 0 if force_cpu else config.llm_gpu_layers

        logger.info(
            f"Loading model '{path.name}' "
            f"(ctx={config.llm_context_size}, threads={n_threads}, "
            f"gpu_layers={n_gpu_layers})"
        )

        try:
            self._llm = Llama(
                model_path=str(path),
                n_ctx=config.llm_context_size,
                n_threads=n_threads,
                n_gpu_layers=n_gpu_layers,
                verbose=False,
            )
            self._model_path = str(path)
            self._model_name = path.stem
            self._gpu_enabled = n_gpu_layers != 0
            logger.info(f"Model loaded successfully: {self._model_name}")

        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            self._llm = None
            raise

    def unload_model(self) -> None:
        """Unload the current model to free memory."""
        if self._llm is not None:
            del self._llm
            self._llm = None
            self._model_path = ""
            self._model_name = ""
            self._gpu_enabled = False
            logger.info("Model unloaded")

    def generate(
        self,
        system_prompt: str = "",
        user_prompt: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.7,
        top_p: float = 0.95,
        stop: Optional[list[str]] = None,
    ) -> str:
        """
        Generate a text response from the LLM.

        Args:
            system_prompt: System-level instructions.
            user_prompt: User message / query.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature (lower = more deterministic).
            top_p: Nucleus sampling threshold.
            stop: Stop sequences.

        Returns:
            Generated text response.
        """
        if self._llm is None:
            raise RuntimeError("No model loaded. Call load_model() first.")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        try:
            result = self._llm.create_chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                stop=stop,
            )

            response_text = result["choices"][0]["message"]["content"]
            return response_text.strip()

        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise

    def list_available_models(self) -> list[dict]:
        """List GGUF model files in the models directory."""
        models = []
        models_dir = config.models_dir
        if models_dir.exists():
            for f in models_dir.glob("*.gguf"):
                size_gb = f.stat().st_size / (1024 ** 3)
                models.append({
                    "name": f.stem,
                    "path": str(f),
                    "size_gb": round(size_gb, 2),
                })
        return models


# Singleton engine instance
llm_engine = LLMEngine()
