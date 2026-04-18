from __future__ import annotations

import asyncio
from typing import Optional

from .base import LLMClient


class GeminiClient(LLMClient):
    """
    Google Gemini via the new `google-genai` SDK.
    Users get a key from https://aistudio.google.com/app/apikey
    """
    name = "gemini"
    default_model = "gemini-2.0-flash"

    def _client(self):
        from google import genai
        return genai.Client(api_key=self.api_key)

    async def vision(self, image_bytes: bytes, prompt: str,
                     mime: str = "image/png") -> str:
        def _call():
            from google.genai import types
            c = self._client()
            resp = c.models.generate_content(
                model=self.model,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime),
                    prompt,
                ],
            )
            return resp.text or ""

        return await asyncio.to_thread(_call)

    async def text(self, prompt: str, system: Optional[str] = None) -> str:
        def _call():
            from google.genai import types
            c = self._client()
            kwargs = dict(model=self.model, contents=prompt)
            if system:
                kwargs["config"] = types.GenerateContentConfig(
                    system_instruction=system,
                )
            resp = c.models.generate_content(**kwargs)
            return resp.text or ""

        return await asyncio.to_thread(_call)
