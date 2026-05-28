"""
OpenAI Chat Completions API backend.

Supports any OpenAI-compatible endpoint (GPT-4o, GPT-4.1, o1, vLLM,
Ollama, Groq, DeepSeek, etc.) by setting OPENAI_BASE_URL.

Usage:
    export OPENAI_API_KEY="sk-..."
    # optional:
    export OPENAI_BASE_URL="http://localhost:8000/v1"  # for local/custom

    python judge.py --backend openai --model openai/gpt-4o --input data.jsonl
"""

import base64
import io
import os

from openai import OpenAI

from backends.base import BaseJudgeBackend

# Image quality settings — balance quality vs payload size
_JPEG_QUALITY = 85
_MAX_IMAGE_EDGE = 2048


class OpenAIBackend(BaseJudgeBackend):
    """
    Judge backed by OpenAI Chat Completions (or any compatible API).

    Parameters
    ----------
    model_name : str
        Model id, e.g. ``openai/gpt-4o``. The ``openai/`` prefix is
        stripped before calling the API.
    max_workers : int
        Concurrent workers. Default 8.
    max_tokens : int
        ``max_tokens`` per completion. Default 4096.
    """

    def __init__(self, model_name: str, max_workers: int = 8,
                 max_tokens: int = 4096, **kwargs):
        super().__init__(model_name, max_workers=max_workers, **kwargs)
        # Strip provider prefix if present
        self._model = model_name.removeprefix("openai/")
        self._max_tokens = max_tokens
        self._client = None  # lazy init on first call

    def _encode_image(self, image) -> str:
        """Convert PIL Image to base64 data URL."""
        # Resize if needed
        w, h = image.size
        if max(w, h) > _MAX_IMAGE_EDGE:
            ratio = _MAX_IMAGE_EDGE / max(w, h)
            image = image.resize((int(w * ratio), int(h * ratio)))

        buf = io.BytesIO()
        fmt = image.format or "JPEG"
        if fmt.upper() == "PNG":
            image = image.convert("RGB")  # JPEG doesn't support alpha
            fmt = "JPEG"
        image.save(buf, format=fmt, quality=_JPEG_QUALITY)
        b64 = base64.b64encode(buf.getvalue()).decode()
        mime = f"image/{fmt.lower()}"
        return f"data:{mime};base64,{b64}"

    def _build_payload(self, item: dict) -> list[dict]:
        """Build OpenAI-format messages."""
        user_text = item["user_text"]
        image = item["image"]
        img_url = self._encode_image(image)

        # Split user_text around <image> placeholder
        if "<image>" in user_text:
            before, after = user_text.split("<image>", 1)
            content: list[dict] = [
                {"type": "text", "text": before},
                {"type": "image_url", "image_url": {"url": img_url,
                                                     "detail": "auto"}},
                {"type": "text", "text": after},
            ]
        else:
            # No placeholder — prepend image then text
            content = [
                {"type": "image_url", "image_url": {"url": img_url,
                                                     "detail": "auto"}},
                {"type": "text", "text": user_text},
            ]

        return [
            {"role": "system", "content": item["system_prompt"]},
            {"role": "user", "content": content},
        ]

    def _call(self, messages: list[dict]) -> str:
        """Send to OpenAI API, return text."""
        if self._client is None:
            self._client = OpenAI(
                api_key=os.environ.get("OPENAI_API_KEY"),
                base_url=os.environ.get("OPENAI_BASE_URL", None),
            )
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=self._max_tokens,
            temperature=0,
            top_p=1,
            seed=42,
        )
        return resp.choices[0].message.content or ""
