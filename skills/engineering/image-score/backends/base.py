"""
Abstract base class for judge backends.

All backends must implement:
  - _build_payload(item) → provider-specific request
  - _call(payload) → str (model output text)
"""

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any


class BaseJudgeBackend(ABC):
    """Every judge backend inherits from this."""

    def __init__(self, model_name: str, max_workers: int = 8, **kwargs):
        self.model_name = model_name
        self.max_workers = max_workers
        self.kwargs = kwargs

    @abstractmethod
    def _build_payload(self, item: dict) -> Any:
        """
        Translate a unified item into a provider-specific request payload.

        Input item:
          {"system_prompt": str, "user_text": str, "image": PIL.Image}

        Returns: anything self._call can consume.
        """
        ...

    @abstractmethod
    def _call(self, payload: Any) -> str:
        """Send the payload to the provider. Returns raw model output text."""
        ...

    def generate_one(self, item: dict) -> str:
        """Single inference. Subclasses rarely need to override this."""
        return self._call(self._build_payload(item))

    def generate_batch(self, items: list[dict]) -> list[str]:
        """
        Batch inference via thread pool.

        Each item: {"system_prompt": str, "user_text": str, "image": PIL.Image}
        Returns list of generated text strings, same order as items.
        """
        results: list[str | None] = [None] * len(items)

        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            future_to_idx = {
                ex.submit(self.generate_one, item): idx
                for idx, item in enumerate(items)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    results[idx] = f"ERROR: {e}"
                    print(f"WARNING: inference failed for item {idx}: {e}")

        return results  # type: ignore[return-value]
