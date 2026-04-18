"""Tests for updater: version discovery + check() logic.

No real git / GitHub calls — we monkeypatch _git and latest_remote.
"""
from __future__ import annotations

import json
import asyncio

import pytest

from app.services import updater


# ---------------- current_version ----------------

def test_current_version_from_git(monkeypatch):
    def fake_git(args, cwd=updater.REPO_ROOT, timeout=30):
        if args[:2] == ["rev-parse", "HEAD"]:
            return (0, "abcdef1234567890abcdef1234567890abcdef12", "")
        if args[:2] == ["status", "--porcelain"]:
            return (0, "", "")
        return (1, "", "unexpected")
    monkeypatch.setattr(updater, "_git", fake_git)

    cur = updater.current_version()
    assert cur["source"] == "git"
    assert cur["short"] == "abcdef1"
    assert cur["dirty"] is False


def test_current_version_git_dirty(monkeypatch):
    def fake_git(args, cwd=updater.REPO_ROOT, timeout=30):
        if args[:2] == ["rev-parse", "HEAD"]:
            return (0, "0" * 40, "")
        if args[:2] == ["status", "--porcelain"]:
            return (0, " M app/main.py\n", "")
        return (1, "", "")
    monkeypatch.setattr(updater, "_git", fake_git)

    cur = updater.current_version()
    assert cur["source"] == "git"
    assert cur["dirty"] is True


def test_current_version_from_file(tmp_path, monkeypatch):
    # git fails
    monkeypatch.setattr(updater, "_git", lambda *a, **kw: (128, "", "not a repo"))
    # VERSION file present
    vf = tmp_path / "VERSION"
    vf.write_text(json.dumps({
        "sha": "1234567890abcdef",
        "built_at": "2026-04-18T09:00:00Z",
    }), encoding="utf-8")
    monkeypatch.setattr(updater, "VERSION_FILE", vf)

    cur = updater.current_version()
    assert cur["source"] == "file"
    assert cur["short"] == "1234567"
    assert cur.get("built_at") == "2026-04-18T09:00:00Z"


def test_current_version_file_plaintext_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "_git", lambda *a, **kw: (128, "", ""))
    vf = tmp_path / "VERSION"
    # Not JSON — just a raw sha
    vf.write_text("deadbeef1234567890", encoding="utf-8")
    monkeypatch.setattr(updater, "VERSION_FILE", vf)

    cur = updater.current_version()
    assert cur["source"] == "file"
    assert cur["short"] == "deadbee"


def test_current_version_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "_git", lambda *a, **kw: (128, "", ""))
    monkeypatch.setattr(updater, "VERSION_FILE", tmp_path / "does-not-exist")

    cur = updater.current_version()
    assert cur["source"] == "unknown"
    assert cur["sha"] == ""


# ---------------- check() ----------------

def test_check_update_available(monkeypatch):
    monkeypatch.setattr(updater, "current_version", lambda: {
        "sha": "aaaaaaa1111", "short": "aaaaaaa", "source": "git", "dirty": False,
    })

    def fake_remote():
        return {"sha": "bbbbbbb2222", "short": "bbbbbbb",
                "message": "feat: stuff", "date": "", "url": ""}
    monkeypatch.setattr(updater, "latest_remote", fake_remote)

    result = asyncio.run(updater.check())
    assert result["available"] is True
    assert result["current"]["short"] == "aaaaaaa"
    assert result["remote"]["short"] == "bbbbbbb"


def test_check_up_to_date(monkeypatch):
    same = "samesha1234"
    monkeypatch.setattr(updater, "current_version", lambda: {
        "sha": same, "short": same[:7], "source": "git", "dirty": False,
    })
    monkeypatch.setattr(updater, "latest_remote", lambda: {
        "sha": same, "short": same[:7], "message": "", "date": "", "url": "",
    })
    result = asyncio.run(updater.check())
    assert result["available"] is False


def test_check_unknown_local_treated_as_update(monkeypatch):
    monkeypatch.setattr(updater, "current_version", lambda: {
        "sha": "", "short": "", "source": "unknown", "dirty": False,
    })
    monkeypatch.setattr(updater, "latest_remote", lambda: {
        "sha": "remote123", "short": "remote1", "message": "", "date": "", "url": "",
    })
    result = asyncio.run(updater.check())
    # Local unknown → tell user there's an update so they get prompted
    assert result["available"] is True


def test_check_network_error_returns_error(monkeypatch):
    monkeypatch.setattr(updater, "current_version", lambda: {
        "sha": "x", "short": "x", "source": "git", "dirty": False,
    })

    def boom():
        raise RuntimeError("network down")
    monkeypatch.setattr(updater, "latest_remote", boom)

    result = asyncio.run(updater.check())
    assert result["available"] is False
    assert "network down" in result["error"]


# ---------------- apply() guards ----------------

def test_apply_refuses_non_git_install(monkeypatch):
    monkeypatch.setattr(updater, "current_version", lambda: {
        "sha": "x", "short": "x", "source": "file", "dirty": False,
    })
    result = asyncio.run(updater.apply())
    assert result["ok"] is False
    assert "git" in result["message"]


def test_apply_refuses_dirty_tree(monkeypatch):
    monkeypatch.setattr(updater, "current_version", lambda: {
        "sha": "x", "short": "x", "source": "git", "dirty": True,
    })
    result = asyncio.run(updater.apply())
    assert result["ok"] is False
    assert "未 commit" in result["message"] or "stash" in result["message"]
