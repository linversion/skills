"""
Google Gemini API backend.

Uses the google-genai SDK. Image is sent as raw bytes (no base64 overhead).
Gemini places system instructions at the model level, not in the message list.

Usage:
    export GOOGLE_API_KEY="..."
    python judge.py --backend gemini --model gemini/gemini-2.5-pro --input data.jsonl
"""

import io
import os

from backends.base import BaseJudgeBackend

_MAX_IMAGE_EDGE = 2048


class GeminiBackend(BaseJudgeBackend):
    """
    Judge backed by Google Gemini via the genai SDK.

    Parameters
    ----------
    model_name : str
        Model id, e.g. ``gemini/gemini-2.5-pro``. The ``gemini/`` prefix
        is stripped before calling the API.
    max_workers : int
        Concurrent workers. Default 8.
    max_tokens : int
        ``max_output_tokens`` per generation. Default 4096.
    """

    def __init__(self, model_name: str, max_workers: int = 8,
                 max_tokens: int = 4096, **kwargs):
        super().__init__(model_name, max_workers=max_workers, **kwargs)
        self._model = model_name.removeprefix("gemini/")
        self._max_tokens = max_tokens
        self._client = None  # lazy init on first call

    def _encode_image_bytes(self, image) -> tuple[bytes, str]:
        """Convert PIL Image to JPEG bytes + mime type."""
        w, h = image.size
        if max(w, h) > _MAX_IMAGE_EDGE:
            ratio = _MAX_IMAGE_EDGE / max(w, h)
            image = image.resize((int(w * ratio), int(h * ratio)))

        buf = io.BytesIO()
        fmt = image.format or "JPEG"
        if fmt.upper() not in ("JPEG", "PNG"):
            image = image.convert("RGB")
            fmt = "JPEG"
        image.save(buf, format=fmt)
        mime = f"image/{fmt.lower()}"
        return buf.getvalue(), mime

    def _build_payload(self, item: dict) -> dict:
        """
        Build Gemini-format payload.

        Returns: {"system_instruction": ..., "contents": [...]}
        """
        from google.genai import types

        user_text = item["user_text"]
        image = item["image"]
        img_bytes, mime_type = self._encode_image_bytes(image)

        system_instruction = item["system_prompt"]
        image_part = types.Part.from_bytes(data=img_bytes, mime_type=mime_type)

        if "<image>" in user_text:
            before, after = user_text.split("<image>", 1)
            parts = []
            if before.strip():
                parts.append(types.Part.from_text(text=before))
            parts.append(image_part)
            if after.strip():
                parts.append(types.Part.from_text(text=after))
        else:
            parts = [
                image_part,
                types.Part.from_text(text=user_text),
            ]

        return {
            "system_instruction": system_instruction,
            "contents": [types.Content(role="user", parts=parts)],
        }

    def _call(self, payload: dict) -> str:
        """Send to Gemini API, return text."""
        if self._client is None:
            from google import genai
            self._client = genai.Client(
                api_key=os.environ.get("GOOGLE_API_KEY"),
            )

        from google.genai import types

        model = self._client.models

        config = types.GenerateContentConfig(
            system_instruction=payload["system_instruction"],
            max_output_tokens=self._max_tokens,
            temperature=0,
            top_p=1,
            seed=42,
        )

        resp = self._client.models.generate_content(
            model=self._model,
            contents=payload["contents"],
            config=config,
        )
        return resp.text or ""
