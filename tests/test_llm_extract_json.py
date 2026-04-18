"""Tests for extract_json — the JSON sponge that tolerates LLM prose + fences."""
from __future__ import annotations

from app.llm.base import extract_json


def test_plain_array():
    assert extract_json('[1, 2, 3]') == [1, 2, 3]


def test_plain_object():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_json_fenced():
    raw = '```json\n[{"x": "y"}]\n```'
    assert extract_json(raw) == [{"x": "y"}]


def test_plain_fenced_no_lang():
    raw = '```\n{"k": 2}\n```'
    assert extract_json(raw) == {"k": 2}


def test_leading_prose_then_array():
    raw = '好的，這是結果：\n[{"name": "王小明"}]'
    assert extract_json(raw) == [{"name": "王小明"}]


def test_trailing_prose_requires_balanced():
    # Model sometimes adds trailing commentary; we should still recover
    raw = '[{"a": 1}]\n以上就是結果'
    assert extract_json(raw) == [{"a": 1}]


def test_empty_returns_none():
    assert extract_json("") is None
    assert extract_json(None) is None


def test_garbage_returns_none():
    assert extract_json("完全沒有 json") is None


def test_nested_object():
    raw = '{"outer": {"inner": [1, 2]}}'
    assert extract_json(raw) == {"outer": {"inner": [1, 2]}}
