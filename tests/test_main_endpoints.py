"""Integration-ish smoke tests for FastAPI endpoints.

We isolate the config file per test and mock out any service that touches
the network / Google / browser / LLM. No real app/data/config.json is ever
written because CONFIG_PATH points at tmp_path.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app import config as appconfig
from app import main as app_main
from app.services import cathlab_service, updater, sheet_service


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(appconfig, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(appconfig, "_cached", None)
    # Sheet reset_cache is called in /api/settings — make it a no-op that
    # also doesn't depend on gspread being configured.
    monkeypatch.setattr(sheet_service, "reset_cache", lambda: None)
    return TestClient(app_main.app)


# ---------------- Page routes ----------------

def test_home_redirects_when_unconfigured(client):
    # Fresh config → is_ready() False → should redirect to /settings
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].endswith("/settings")


def test_home_renders_when_configured(client, tmp_path, monkeypatch):
    # Fill minimum fields so is_ready() passes
    creds_file = tmp_path / "creds.json"
    creds_file.write_text("{}", encoding="utf-8")
    appconfig.update(
        llm_provider="gemini", llm_api_key="AIzaXXX",
        google_creds_path=str(creds_file), sheet_id="FAKE_ID",
    )
    r = client.get("/")
    assert r.status_code == 200
    # index.html template should mention 入院
    assert "入院" in r.text or "admission" in r.text.lower()


def test_settings_page_renders(client):
    r = client.get("/settings")
    assert r.status_code == 200
    # Form should include provider input
    assert "llm_provider" in r.text or "設定" in r.text


# ---------------- /api/settings POST ----------------

def test_save_settings_ok(client):
    r = client.post("/api/settings", data={
        "llm_provider": "anthropic",
        "llm_api_key": "sk-ant-xxx",
        "llm_model": "",
        "google_creds_path": "/tmp/x.json",
        "sheet_id": "ABC123",
    })
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    cfg = appconfig.load()
    assert cfg.llm_provider == "anthropic"
    assert cfg.llm_api_key == "sk-ant-xxx"
    assert cfg.sheet_id == "ABC123"


def test_save_settings_blank_api_key_preserves_existing(client):
    # First save with a key
    client.post("/api/settings", data={
        "llm_provider": "openai",
        "llm_api_key": "sk-original",
        "google_creds_path": "/tmp/a.json",
        "sheet_id": "XID",
    })
    # Second save with blank key — should NOT wipe
    r = client.post("/api/settings", data={
        "llm_provider": "openai",
        "llm_api_key": "",          # blank
        "google_creds_path": "/tmp/a.json",
        "sheet_id": "XID",
    })
    assert r.status_code == 200
    cfg = appconfig.load()
    assert cfg.llm_api_key == "sk-original"


def test_save_settings_trims_whitespace(client):
    r = client.post("/api/settings", data={
        "llm_provider": "  gemini  ",
        "llm_api_key": "  AIzaXXX  ",
        "google_creds_path": "  /tmp/x.json  ",
        "sheet_id": "  ABC  ",
    })
    assert r.status_code == 200
    cfg = appconfig.load()
    assert cfg.llm_provider == "gemini"
    assert cfg.llm_api_key == "AIzaXXX"
    assert cfg.sheet_id == "ABC"


# ---------------- /api/update/check ----------------

def test_update_check_routes_through_updater(client, monkeypatch):
    async def fake_check():
        return {"available": True, "current": {"short": "aaa"},
                "remote": {"short": "bbb"}, "repo_url": "https://x"}
    monkeypatch.setattr(updater, "check", fake_check)

    r = client.get("/api/update/check")
    assert r.status_code == 200
    data = r.json()
    assert data["available"] is True
    assert data["remote"]["short"] == "bbb"


def test_update_apply_non_git_message(client, monkeypatch):
    # current_version returns source=file → apply() returns ok=False
    monkeypatch.setattr(updater, "current_version", lambda: {
        "sha": "x", "short": "x", "source": "file", "dirty": False,
    })
    r = client.post("/api/update/apply", data={"restart": "no"})
    assert r.status_code == 200
    assert r.json()["ok"] is False


# ---------------- /api/step5/plan ----------------

def test_step5_plan_routes_through_cathlab_service(client, monkeypatch):
    # Avoid hitting the real Sheet by stubbing read_patients
    monkeypatch.setattr(cathlab_service, "read_patients",
                        lambda d: [{"seq": 1, "doctor": "詹世鴻",
                                    "name": "王小明", "chart": "12345678",
                                    "diag": "CAD", "cath": "Left heart cath.",
                                    "note": "", "skip": False}])
    r = client.get("/api/step5/plan", params={"date": "20260410"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    # plan keyed by cath_date
    assert "2026/04/10" in data["plan"]
    entry = data["plan"]["2026/04/10"][0]
    assert entry["session"] == "AM"
    assert entry["room"] == "C2"


# ---------------- /api/sheet/list error propagation ----------------

def test_sheet_list_error_returns_500(client, monkeypatch):
    def boom():
        raise RuntimeError("no creds")
    monkeypatch.setattr(sheet_service, "list_sheets", boom)
    r = client.get("/api/sheet/list")
    assert r.status_code == 500
    assert "no creds" in r.text
