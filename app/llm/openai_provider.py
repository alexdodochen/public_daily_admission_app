from __future__ import annotations

import asyncio
import base64
from typing import Optional

from .base import LLMClient


class OpenAIClient(LLMClient):
    name = "openai"
    default_model = "gpt-4o"

    def _client(self):
        from openai import OpenAI
        return OpenAI(api_key=self.api_key)

    async def vision(self, image_bytes: bytes, prompt: str,
                     mime: str = "image/png") -> str:
        b64 = base64.standard_b64encode(image_bytes).decode()
        data_url = f"data:{mime};base64,{b64}"

        def _call():
            c = self._client()
            resp = c.chat.completions.create(
                model=self.model,
                max_tokens=4096,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }],
            )
            return resp.choices[0].message.content or ""

        return await asyncio.to_thread(_call)

    async def text(self, prompt: str, system: Optional[str] = None) -> str:
        def _call():
            c = self._client()
            msgs = []
            if system:
                msgs.append({"role": "system", "content": system})
            msgs.append({"role": "user", "content": prompt})
            resp = c.chat.completions.create(
                model=self.model, max_tokens=4096, messages=msgs,
            )
            return resp.choices[0].message.content or ""

        return await asyncio.to_thread(_call)
