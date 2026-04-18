from __future__ import annotations

import asyncio
import base64
from typing import Optional

from .base import LLMClient


class AnthropicClient(LLMClient):
    name = "anthropic"
    default_model = "claude-sonnet-4-6"

    def _client(self):
        from anthropic import Anthropic
        return Anthropic(api_key=self.api_key)

    async def vision(self, image_bytes: bytes, prompt: str,
                     mime: str = "image/png") -> str:
        b64 = base64.standard_b64encode(image_bytes).decode()

        def _call():
            c = self._client()
            msg = c.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {
                            "type": "base64", "media_type": mime, "data": b64,
                        }},
                        {"type": "text", "text": prompt},
                    ],
                }],
            )
            return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")

        return await asyncio.to_thread(_call)

    async def text(self, prompt: str, system: Optional[str] = None) -> str:
        def _call():
            c = self._client()
            kwargs = dict(model=self.model, max_tokens=4096,
                          messages=[{"role": "user", "content": prompt}])
            if system:
                kwargs["system"] = system
            msg = c.messages.create(**kwargs)
            return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")

        return await asyncio.to_thread(_call)
