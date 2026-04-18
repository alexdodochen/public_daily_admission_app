"""Tests for ocr_service — focus on the normalization step after LLM returns
JSON. Mocks the LLM so no real API call happens."""
from __future__ import annotations

import asyncio

import pytest

from app.services import ocr_service


class FakeLLM:
    """Stub LLM that always returns the configured payload for vision()."""
    def __init__(self, payload: str):
        self.payload = payload
        self.calls = 0

    async def vision(self, image_bytes, prompt, mime="image/png"):
        self.calls += 1
        return self.payload

    async def text(self, prompt, system=None):
        return ""


def _run(coro):
    return asyncio.run(coro)


def test_ocr_normalizes_all_12_keys(monkeypatch):
    # LLM gives back 1 full row + 1 partial row
    payload = """[
      {"admit_date": "2026/04/20", "op_date": "", "department": "心內",
       "doctor": "李文煌", "icd_diagnosis": "I25.10 CAD", "name": "王小明",
       "gender": "男", "age": 65, "chart_no": "12345678", "bed": "11A-01",
       "hint": "", "urgent": ""},
      {"name": "林大美", "chart_no": "99999999"}
    ]"""
    fake = FakeLLM(payload)
    monkeypatch.setattr(ocr_service, "get_llm", lambda: fake)

    out = _run(ocr_service.ocr_image(b"fakepng"))
    assert len(out) == 2
    # Row 0 — full
    assert out[0]["doctor"] == "李文煌"
    assert out[0]["age"] == "65"  # coerced to str
    assert out[0]["chart_no"] == "12345678"
    # Row 1 — partial, every missing key defaults to ""
    r1 = out[1]
    expected_keys = {"admit_date", "op_date", "department", "doctor",
                     "icd_diagnosis", "name", "gender", "age",
                     "chart_no", "bed", "hint", "urgent"}
    assert set(r1.keys()) == expected_keys
    assert r1["name"] == "林大美"
    assert r1["department"] == ""
    assert r1["doctor"] == ""


def test_ocr_strips_whitespace(monkeypatch):
    fake = FakeLLM('[{"name": "  王小明  ", "chart_no": " 12345 "}]')
    monkeypatch.setattr(ocr_service, "get_llm", lambda: fake)
    out = _run(ocr_service.ocr_image(b""))
    assert out[0]["name"] == "王小明"
    assert out[0]["chart_no"] == "12345"


def test_ocr_skips_non_dict_rows(monkeypatch):
    fake = FakeLLM('[{"name": "A"}, "garbage", 42, null, {"name": "B"}]')
    monkeypatch.setattr(ocr_service, "get_llm", lambda: fake)
    out = _run(ocr_service.ocr_image(b""))
    assert [r["name"] for r in out] == ["A", "B"]


def test_ocr_accepts_fenced_json(monkeypatch):
    fake = FakeLLM('```json\n[{"name": "甲"}]\n```')
    monkeypatch.setattr(ocr_service, "get_llm", lambda: fake)
    out = _run(ocr_service.ocr_image(b""))
    assert out == [{
        "admit_date": "", "op_date": "", "department": "", "doctor": "",
        "icd_diagnosis": "", "name": "甲", "gender": "", "age": "",
        "chart_no": "", "bed": "", "hint": "", "urgent": "",
    }]


def test_ocr_raises_when_not_list(monkeypatch):
    fake = FakeLLM('{"not": "a list"}')
    monkeypatch.setattr(ocr_service, "get_llm", lambda: fake)
    with pytest.raises(ValueError, match="陣列"):
        _run(ocr_service.ocr_image(b""))


def test_ocr_raises_on_total_garbage(monkeypatch):
    fake = FakeLLM("完全無法解析")
    monkeypatch.setattr(ocr_service, "get_llm", lambda: fake)
    with pytest.raises(ValueError):
        _run(ocr_service.ocr_image(b""))
