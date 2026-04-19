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


# --------------------------- diff_main_data ---------------------------

def _ex(chart, name="", doctor=""):
    """Build a 12-col A-L row with chart_no at index 8."""
    return ["", "", "", doctor, "", name, "", "", chart, "", "", ""]


def _new(chart, name="", doctor=""):
    return {"chart_no": chart, "name": name, "doctor": doctor}


def test_diff_first_time_sheet_empty():
    d = ocr_service.diff_main_data([], [_new("111", "甲", "李文煌")])
    assert d["existing_count"] == 0
    assert d["new_count"] == 1
    assert len(d["added"]) == 1
    assert d["added"][0]["chart_no"] == "111"
    assert d["removed"] == [] and d["kept"] == []


def test_diff_all_kept_no_changes():
    existing = [_ex("111", "甲", "李文煌"), _ex("222", "乙", "柯呈諭")]
    new = [_new("111", "甲", "李文煌"), _new("222", "乙", "柯呈諭")]
    d = ocr_service.diff_main_data(existing, new)
    assert len(d["kept"]) == 2
    assert d["added"] == [] and d["removed"] == []
    assert d["doctor_changed"] == []


def test_diff_detects_added_and_removed():
    existing = [_ex("111", "甲"), _ex("222", "乙")]
    new = [_new("222", "乙"), _new("333", "丙")]
    d = ocr_service.diff_main_data(existing, new)
    assert [x["chart_no"] for x in d["added"]]   == ["333"]
    assert [x["chart_no"] for x in d["removed"]] == ["111"]
    assert [x["chart_no"] for x in d["kept"]]    == ["222"]


def test_diff_detects_doctor_change():
    existing = [_ex("111", "甲", "李文煌")]
    new = [_new("111", "甲", "柯呈諭")]
    d = ocr_service.diff_main_data(existing, new)
    assert d["kept"][0]["doctor_old"] == "李文煌"
    assert d["kept"][0]["doctor_new"] == "柯呈諭"
    assert d["doctor_changed"] == [
        {"chart_no": "111", "name": "甲", "old": "李文煌", "new": "柯呈諭"}
    ]


def test_diff_reports_unmatched_chartless_rows():
    # A row with name but no chart_no → unmatched (can't be diffed)
    existing = [["", "", "", "", "", "幽靈", "", "", "", "", "", ""]]
    new = [_new("", "無號新")]
    d = ocr_service.diff_main_data(existing, new)
    assert d["unmatched_existing"] == [0]
    assert d["unmatched_new"] == [0]


def test_diff_ignores_fully_blank_rows():
    existing = [_ex("111", "甲"), ["", "", "", "", "", "", "", "", "", "", "", ""]]
    new = [_new("111", "甲")]
    d = ocr_service.diff_main_data(existing, new)
    assert d["unmatched_existing"] == []
    assert len(d["kept"]) == 1


def test_plan_write_returns_first_time_shape_when_sheet_missing(monkeypatch):
    monkeypatch.setattr(ocr_service.sheet_service, "get_worksheet",
                        lambda name: None)
    r = ocr_service.plan_write("20260501", [_new("111", "甲")])
    assert r["sheet_has_data"] is False
    assert r["new_count"] == 1
    assert r["added"] == []  # added/removed only meaningful vs existing sheet


def test_write_to_sheet_refuses_overwrite_without_confirm(monkeypatch):
    """If sheet already has data and allow_overwrite=False → return diff, no write."""

    class FakeWS:
        id = 999

    fake_ws = FakeWS()
    write_calls = []
    monkeypatch.setattr(ocr_service.sheet_service, "ensure_date_sheet",
                        lambda d: fake_ws)
    monkeypatch.setattr(
        ocr_service.sheet_service, "read_range",
        lambda ws, a1: [_ex("111", "甲", "李文煌")],
    )
    monkeypatch.setattr(
        ocr_service.sheet_service, "write_range",
        lambda *a, **kw: write_calls.append((a, kw)),
    )
    r = ocr_service.write_to_sheet(
        "20260501", [_new("222", "乙", "柯呈諭")], allow_overwrite=False
    )
    assert r["needs_confirm"] is True
    assert len(r["added"]) == 1
    assert len(r["removed"]) == 1
    assert write_calls == []   # nothing written


def test_write_to_sheet_applies_when_confirmed(monkeypatch):
    class FakeWS:
        id = 999
    fake_ws = FakeWS()
    write_calls = []
    monkeypatch.setattr(ocr_service.sheet_service, "ensure_date_sheet",
                        lambda d: fake_ws)
    monkeypatch.setattr(
        ocr_service.sheet_service, "read_range",
        lambda ws, a1: [_ex("111", "甲")],
    )
    monkeypatch.setattr(
        ocr_service.sheet_service, "write_range",
        lambda ws, a1, body, raw=False: write_calls.append((a1, body)),
    )
    r = ocr_service.write_to_sheet(
        "20260501",
        [_new("222", "乙", "柯呈諭"), _new("333", "丙", "李文煌")],
        allow_overwrite=True,
    )
    assert r["needs_confirm"] is False
    assert r["rows"] == 2
    assert len(write_calls) == 1
    assert write_calls[0][0] == "A2:L3"
