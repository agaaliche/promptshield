"""LLM package — local (llama.cpp) and remote (OpenAI-compatible) engines."""
from core.llm.engine import LLMEngine, llm_engine  # noqa: F401
from core.llm.remote_engine import RemoteLLMEngine, remote_llm_engine  # noqa: F401
