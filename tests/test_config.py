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

    Also point bundled-resource paths to nonexistent locations so the
    dev-tree's app/bundled/defaults.json doesn't bleed into tests that
    assert on empty defaults. Tests that want to exercise bundling
    re-monkeypatch these.
    """
    monkeypatch.setattr(appconfig, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(appconfig, "BUNDLED_DEFAULTS", tmp_path / "no-defaults.json")
    monkeypatch.setattr(appconfig, "BUNDLED_SA",       tmp_path / "no-sa.json")
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


# ----------------------- bundled defaults layering -----------------------

def test_bundled_defaults_fill_empty_fields(tmp_path, monkeypatch):
    bundle = tmp_path / "defaults.json"
    bundle.write_text(json.dumps({
        "sheet_id": "BUNDLED_SHEET_ID",
        "emr_base_url": "http://bundled-emr/",
        "cathlab_base_url": "http://bundled-cvis/",
    }), encoding="utf-8")
    monkeypatch.setattr(appconfig, "BUNDLED_DEFAULTS", bundle)
    cfg = appconfig.load()
    assert cfg.sheet_id == "BUNDLED_SHEET_ID"
    assert cfg.emr_base_url == "http://bundled-emr/"
    assert cfg.cathlab_base_url == "http://bundled-cvis/"


def test_user_config_overrides_bundled(tmp_path, monkeypatch):
    bundle = tmp_path / "defaults.json"
    bundle.write_text(json.dumps({"sheet_id": "BUNDLED"}), encoding="utf-8")
    monkeypatch.setattr(appconfig, "BUNDLED_DEFAULTS", bundle)
    # User already picked their own sheet
    appconfig.CONFIG_PATH.write_text(
        json.dumps({"sheet_id": "USER_PICKED"}), encoding="utf-8",
    )
    cfg = appconfig.load()
    assert cfg.sheet_id == "USER_PICKED"


def test_bundled_sa_fills_empty_creds_path(tmp_path, monkeypatch):
    sa_file = tmp_path / "sa.json"
    sa_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(appconfig, "BUNDLED_SA", sa_file)
    cfg = appconfig.load()
    assert cfg.google_creds_path == str(sa_file)


def test_bundled_sa_does_not_override_user_path(tmp_path, monkeypatch):
    sa_file = tmp_path / "sa.json"
    sa_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(appconfig, "BUNDLED_SA", sa_file)
    appconfig.CONFIG_PATH.write_text(
        json.dumps({"google_creds_path": "C:/my/own/creds.json"}),
        encoding="utf-8",
    )
    cfg = appconfig.load()
    assert cfg.google_creds_path == "C:/my/own/creds.json"


def test_bundled_flags_reports_what_is_available(tmp_path, monkeypatch):
    bundle = tmp_path / "defaults.json"
    bundle.write_text(json.dumps({
        "sheet_id": "X",
        "emr_base_url": "Y",
    }), encoding="utf-8")
    monkeypatch.setattr(appconfig, "BUNDLED_DEFAULTS", bundle)
    # No bundled SA
    flags = appconfig.bundled_flags()
    assert flags["sheet_id"] is True
    assert flags["emr_base_url"] is True
    assert flags["cathlab_base_url"] is False
    assert flags["google_creds_path"] is False


def test_bundled_defaults_missing_file_is_noop(monkeypatch):
    # Already pointed at nonexistent path by fixture
    cfg = appconfig.load()
    assert cfg.sheet_id == ""


def test_bundled_defaults_corrupt_json_is_noop(tmp_path, monkeypatch):
    bundle = tmp_path / "defaults.json"
    bundle.write_text("{not valid", encoding="utf-8")
    monkeypatch.setattr(appconfig, "BUNDLED_DEFAULTS", bundle)
    cfg = appconfig.load()
    assert cfg.sheet_id == ""  # falls back silently
