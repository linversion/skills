"""
Judge backend registry.

Add a new backend:
  1. Create backends/your_backend.py (inherit from BaseJudgeBackend)
  2. Register it here in BACKENDS
  3. Use: python judge.py --backend your --model your/model-name
"""

from backends.base import BaseJudgeBackend
from backends.openai_backend import OpenAIBackend
from backends.gemini_backend import GeminiBackend

BACKENDS: dict[str, type[BaseJudgeBackend]] = {
    "openai": OpenAIBackend,
    "gemini": GeminiBackend,
}


def create_judge(backend: str, model: str, **kwargs) -> BaseJudgeBackend:
    """Create a judge instance for the given backend."""
    cls = BACKENDS.get(backend)
    if cls is None:
        keys = ", ".join(BACKENDS.keys())
        raise ValueError(
            f"Unknown backend '{backend}'. Available: {keys}"
        )
    return cls(model_name=model, **kwargs)
