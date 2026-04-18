"""More cathlab_service tests — _enrich, _build_json, _read_w_markers,
plan(), keyin(dry_run=True), get_cathlab_date edge cases."""
from __future__ import annotations

import asyncio
import json

import pytest

from app.services import cathlab_service as cs


# ---------------- _build_json ----------------

def test_build_json_empty_id_returns_empty_string():
    assert cs._build_json("CAD", "") == ""
    assert cs._build_json("", "") == ""


def test_build_json_preserves_chinese_without_escape():
    result = cs._build_json("術前診斷", "PDI20090908120009")
    parsed = json.loads(result)
    assert parsed == [{"name": "術前診斷", "id": "PDI20090908120009"}]
    # ensure_ascii=False means the Chinese bytes appear literally
    assert "術" in result


# ---------------- _read_w_markers ----------------

def test_read_w_markers_skips_rows_without_w():
    # 23-column rows: chart is idx 18 (S), W is idx 22
    grid = [
        [""] * 18 + ["12345678"] + [""] * 4,      # has chart, no W
        [""] * 18 + ["99999999"] + ["", "", "", "20260420"],  # has W
        [""] * 18 + ["11111111"] + ["", "", "", "改期"],       # header-ish, skipped
    ]
    markers = cs._read_w_markers(grid)
    assert markers == {"99999999": "20260420"}


def test_read_w_markers_ignores_short_rows():
    grid = [["x"] * 10]  # only 10 cols, can't reach idx 22
    assert cs._read_w_markers(grid) == {}


def test_read_w_markers_empty():
    assert cs._read_w_markers([]) == {}


# ---------------- get_cathlab_date — extra weekdays ----------------

def test_wednesday_plus_one():
    # 2026-04-15 is Wed → Thu
    assert cs.get_cathlab_date("20260415", "陳儒逸", "") == "2026/04/16"


def test_sunday_plus_one():
    # 2026-04-12 is Sun → Mon
    assert cs.get_cathlab_date("20260412", "詹世鴻", "") == "2026/04/13"


# ---------------- _enrich ----------------

def _mk_patient(**kw):
    base = {"seq": 1, "doctor": "詹世鴻", "name": "王小明",
            "chart": "12345678", "diag": "CAD", "cath": "Left heart cath.",
            "note": "", "skip": False}
    base.update(kw)
    return base


def test_enrich_skip_clears_all_derived_fields():
    p = _mk_patient(skip=True, note="備註檢查")
    out = cs._enrich([p], "20260410")[0]
    assert out["cath_date"] == ""
    assert out["session"] == ""
    assert out["room"] == ""
    assert out["time"] == ""
    assert out["diag_id"] == ""
    assert out["proc_id"] == ""
    assert out["second_doctor"] == ""
    assert out["note_out"] == "備註檢查"  # original preserved


def test_enrich_scheduled_doctor_populates_slot():
    # 詹世鴻 週五（2026-04-10）AM C2
    p = _mk_patient(doctor="詹世鴻")
    out = cs._enrich([p], "20260410")[0]
    assert out["cath_date"] == "2026/04/10"
    assert out["session"] == "AM"
    assert out["room"] == "C2"
    assert out["time"] == "0600"
    assert out["diag_id"] == "PDI20090908120009"
    assert out["proc_id"] == "PHC20090907120001"


def test_enrich_non_schedule_appends_marker():
    # 測試醫師 has no schedule → OFF + 本日無時段
    p = _mk_patient(doctor="測試醫師", note="")
    out = cs._enrich([p], "20260413")[0]
    assert out["session"] == "OFF"
    assert out["room"] == "H1"
    assert "本日無時段" in out["note_out"]
    # Time starts at 2100 block
    assert out["time"].startswith("21") or out["time"].startswith("22")


def test_enrich_non_schedule_marker_not_duplicated():
    p = _mk_patient(doctor="測試醫師", note="本日無時段 已註")
    out = cs._enrich([p], "20260413")[0]
    assert out["note_out"].count("本日無時段") == 1


def test_enrich_unmapped_procedure_goes_to_note():
    p = _mk_patient(cath="特殊手術XYZ")
    out = cs._enrich([p], "20260410")[0]
    assert out["proc_id"] == ""
    assert "特殊手術XYZ" in out["note_out"]


def test_enrich_pm_hint_picks_pm_slot():
    # 柯呈諭 週四 (2026-04-16) 有 AM+PM 兩個 slot
    p = _mk_patient(doctor="柯呈諭", note="病人要求下午")
    out = cs._enrich([p], "20260415")[0]  # 週三入院 → N+1=週四
    assert out["session"] == "PM"
    assert out["time"] == "1800"


def test_enrich_am_hint_picks_am_slot():
    p = _mk_patient(doctor="柯呈諭", note="上午處理")
    out = cs._enrich([p], "20260415")[0]
    assert out["session"] == "AM"


def test_enrich_zhang_tuesday_same_day_forces_pm():
    # 2026-04-14 Tue, 張獻元 自己時段 → 同日 PM
    p = _mk_patient(doctor="張獻元", note="")
    out = cs._enrich([p], "20260414")[0]
    assert out["cath_date"] == "2026/04/14"  # same-day per get_cathlab_date rule
    assert out["session"] == "PM"


def test_enrich_increments_time_per_doctor():
    # Three patients same doctor same day → 0600, 0601, 0602
    pts = [_mk_patient(doctor="詹世鴻", chart=str(i), name=f"P{i}") for i in range(3)]
    out = cs._enrich(pts, "20260410")
    times = [p["time"] for p in out]
    assert times == ["0600", "0601", "0602"]


def test_enrich_counts_per_doctor_independently():
    # Two doctors same day → each starts at 0600
    pts = [
        _mk_patient(doctor="詹世鴻", chart="1"),  # Fri AM C2 → 0600
        _mk_patient(doctor="陳儒逸", chart="2"),  # Fri AM C1 → 0600
    ]
    out = cs._enrich(pts, "20260410")
    assert out[0]["time"] == "0600"
    assert out[1]["time"] == "0600"
    assert out[0]["room"] != out[1]["room"]


def test_enrich_second_doctor_from_note():
    p = _mk_patient(note="浩")
    out = cs._enrich([p], "20260410")[0]
    assert out["second_doctor"] == "葉立浩"


# ---------------- plan() ----------------

def test_plan_groups_by_cath_date(monkeypatch):
    patients = [
        _mk_patient(doctor="詹世鴻", chart="1", name="A"),
        _mk_patient(doctor="詹世鴻", chart="2", name="B"),
        _mk_patient(doctor="測試醫師", chart="3", name="C", skip=True),
    ]
    monkeypatch.setattr(cs, "read_patients", lambda d: patients)
    result = cs.plan("20260410")

    assert result["admit_date"] == "20260410"
    # Two active patients grouped by cath_date
    assert "2026/04/10" in result["plan"]
    assert len(result["plan"]["2026/04/10"]) == 2
    assert len(result["skipped"]) == 1


def test_plan_empty_patients(monkeypatch):
    monkeypatch.setattr(cs, "read_patients", lambda d: [])
    result = cs.plan("20260410")
    assert result["plan"] == {}
    assert result["skipped"] == []


# ---------------- keyin(dry_run=True) ----------------

def test_keyin_dry_run_skips_browser(monkeypatch):
    patients = [_mk_patient(doctor="詹世鴻", chart="1")]
    monkeypatch.setattr(cs, "read_patients", lambda d: patients)
    # Sentinel: if something tries to import playwright, this would catch it.
    # But dry_run shouldn't even get there.

    result = asyncio.run(cs.keyin("20260410", dry_run=True))
    assert result["dry_run"] is True
    assert len(result["would_add"]) == 1
    assert result["would_add"][0]["cath_date"] == "2026/04/10"
    assert "implemented" not in result  # real-run only key


def test_keyin_real_without_creds_raises(monkeypatch):
    """Without cathlab creds configured, real keyin fails fast before
    touching Playwright."""
    patients = [_mk_patient()]
    monkeypatch.setattr(cs, "read_patients", lambda d: patients)
    # Force an empty config so creds are missing
    from app import config as appconfig
    empty = appconfig.AppConfig()  # all blanks
    monkeypatch.setattr(appconfig, "load", lambda: empty)

    with pytest.raises(RuntimeError, match="WEBCVIS"):
        asyncio.run(cs.keyin("20260410", dry_run=False))
