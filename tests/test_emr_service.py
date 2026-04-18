"""Tests for emr_service.summarize_html — short-circuits on empty input
and otherwise delegates to LLM text()."""
from __future__ import annotations

import asyncio

from app.services import emr_service


class FakeLLM:
    def __init__(self, reply: str):
        self.reply = reply
        self.last_prompt = ""

    async def vision(self, image_bytes, prompt, mime="image/png"):
        return ""

    async def text(self, prompt, system=None):
        self.last_prompt = prompt
        return self.reply


def _run(coro):
    return asyncio.run(coro)


def test_summarize_empty_html_shortcuts_without_llm(monkeypatch):
    sentinel = {"called": False}

    def fake_get():
        sentinel["called"] = True
        return FakeLLM("不該被呼叫")
    monkeypatch.setattr(emr_service, "get_llm", fake_get)

    out = _run(emr_service.summarize_html(""))
    assert "主訴" in out and "—" in out  # dashes placeholder
    assert sentinel["called"] is False


def test_summarize_whitespace_only_shortcuts(monkeypatch):
    monkeypatch.setattr(emr_service, "get_llm",
                        lambda: (_ for _ in ()).throw(AssertionError("shouldn't call")))
    out = _run(emr_service.summarize_html("   \n\t  "))
    assert out.startswith("主訴：")


def test_summarize_delegates_to_llm_and_trims(monkeypatch):
    fake = FakeLLM("主訴：胸痛\n病史：HTN\n理學檢查：—\n檢查結果：Troponin 0.01\n\n")
    monkeypatch.setattr(emr_service, "get_llm", lambda: fake)
    out = _run(emr_service.summarize_html("<div class='small'>SOAP note...</div>"))
    assert out.endswith("Troponin 0.01")  # trimmed trailing \n
    # Prompt should include the HTML (truncated to 15k)
    assert "SOAP note" in fake.last_prompt


def test_summarize_truncates_long_html(monkeypatch):
    huge = "x" * 50000
    fake = FakeLLM("主訴：—\n病史：—\n理學檢查：—\n檢查結果：—")
    monkeypatch.setattr(emr_service, "get_llm", lambda: fake)
    _run(emr_service.summarize_html(huge))
    # Prompt = SUMMARY_PROMPT + html[:15000]. Total length bounded.
    assert len(fake.last_prompt) <= len(emr_service.SUMMARY_PROMPT) + 15000
