"""
Minimal LLM abstraction. Each provider implements two methods.

We keep it tiny: vision (image + prompt -> text) and text (prompt -> text).
Callers parse JSON out of the text response themselves.
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Optional


class LLMClient(ABC):
    name: str = "base"
    default_model: str = ""

    def __init__(self, api_key: str, model: str = ""):
        self.api_key = api_key
        self.model = model or self.default_model

    @abstractmethod
    async def vision(self, image_bytes: bytes, prompt: str,
                     mime: str = "image/png") -> str:
        """Send an image + prompt. Return raw text."""

    @abstractmethod
    async def text(self, prompt: str, system: Optional[str] = None) -> str:
        """Send a text prompt. Return raw text."""


def extract_json(raw: str):
    """
    Pull the first JSON object/array out of a model response,
    tolerating ```json fences and leading prose.
    """
    if not raw:
        return None
    # Strip ```json ... ``` fences
    m = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
    candidate = m.group(1).strip() if m else raw.strip()
    # Trim prose before the first JSON opener — whichever appears earliest.
    positions = [(candidate.find(c), c) for c in "[{"]
    positions = [(i, c) for i, c in positions if i != -1]
    if positions:
        start_i, _ = min(positions)
        candidate = candidate[start_i:]
    try:
        return json.loads(candidate)
    except Exception:
        # Try to locate a balanced block
        stack = []
        start = None
        for i, ch in enumerate(candidate):
            if ch in "{[":
                if start is None:
                    start = i
                stack.append(ch)
            elif ch in "}]" and stack:
                stack.pop()
                if not stack and start is not None:
                    try:
                        return json.loads(candidate[start:i + 1])
                    except Exception:
                        return None
        return None
