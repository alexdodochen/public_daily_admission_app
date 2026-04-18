"""Tests for app.config — load / save / update / is_ready round-trip.

Uses tmp_path to isolate from the real app/data/config.json.
"""
from __future__ import annotations

import json

import pytest

from app import config as appconfig


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    """Redirect CONFIG_PATH to a temp file AND reset the module-level cache.

    Without the cache reset, tests would leak into each other via `_cached`.
    """
    monkeypatch.setattr(appconfig, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(appconfig, "_cached", None)
    yield


def test_load_no_file_returns_defaults():
    cfg = appconfig.load()
    assert cfg.llm_provider == ""
    assert cfg.llm_api_key == ""
    assert cfg.sheet_id == ""
    # Has the documented default EMR URL baked in
    assert "hisweb" in cfg.emr_base_url
    assert cfg.is_ready() is False


def test_load_cached_between_calls():
    cfg1 = appconfig.load()
    cfg2 = appconfig.load()
    assert cfg1 is cfg2  # same instance — cached


def test_save_then_load_roundtrip():
    cfg = appconfig.load()
    cfg.llm_provider = "anthropic"
    cfg.llm_api_key = "sk-ant-test"
    cfg.sheet_id = "1AbC"
    cfg.google_creds_path = "/tmp/creds.json"
    appconfig.save(cfg)

    # Fresh cache
    appconfig._cached = None
    fresh = appconfig.load()
    assert fresh.llm_provider == "anthropic"
    assert fresh.llm_api_key == "sk-ant-test"
    assert fresh.sheet_id == "1AbC"


def test_is_ready_requires_four_fields():
    cfg = appconfig.AppConfig()
    assert cfg.is_ready() is False
    cfg.llm_provider = "gemini"
    cfg.llm_api_key = "AIza..."
    assert cfg.is_ready() is False  # still missing sheet + creds
    cfg.google_creds_path = "/x/y.json"
    cfg.sheet_id = "ABC"
    assert cfg.is_ready() is True


def test_update_partial_fields():
    appconfig.update(llm_provider="openai", llm_api_key="sk-test", sheet_id="ZZZ")

    appconfig._cached = None
    cfg = appconfig.load()
    assert cfg.llm_provider == "openai"
    assert cfg.llm_api_key == "sk-test"
    assert cfg.sheet_id == "ZZZ"
    # untouched
    assert cfg.google_creds_path == ""


def test_update_ignores_unknown_keys():
    # Should not raise; extra keys silently dropped
    appconfig.update(llm_provider="gemini", bogus_field="zzz")
    cfg = appconfig.load()
    assert cfg.llm_provider == "gemini"
    assert not hasattr(cfg, "bogus_field")


def test_update_ignores_none_values():
    appconfig.update(llm_provider="anthropic", llm_api_key="original")
    appconfig.update(llm_provider=None, llm_api_key="new_key")
    cfg = appconfig.load()
    # llm_provider stayed because None was filtered
    assert cfg.llm_provider == "anthropic"
    assert cfg.llm_api_key == "new_key"


def test_load_corrupt_json_returns_defaults(monkeypatch):
    # Write garbage to the config path
    appconfig.CONFIG_PATH.write_text("{not valid json", encoding="utf-8")
    cfg = appconfig.load()
    assert cfg.llm_provider == ""
    assert cfg.is_ready() is False


def test_load_drops_unknown_keys_from_disk():
    # Someone hand-edited the JSON with stray keys
    data = {"llm_provider": "gemini", "llm_api_key": "k", "nonsense_key": 42}
    appconfig.CONFIG_PATH.write_text(json.dumps(data), encoding="utf-8")
    cfg = appconfig.load()
    assert cfg.llm_provider == "gemini"
    assert cfg.llm_api_key == "k"
    assert not hasattr(cfg, "nonsense_key")
