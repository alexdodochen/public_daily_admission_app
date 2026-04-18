"""Pure-logic tests for ordering_service.parse_subtables_grid."""
from __future__ import annotations

from app.services import ordering_service as os_


def _pad(cells, width=8):
    return cells + [""] * (width - len(cells))


def test_parse_single_doctor_table():
    # grid layout:
    # row 1: main header (不被解析)
    # row 5: "柯呈諭（2人）" title at col A
    # row 6: sub-header (skipped)
    # row 7: patient 1
    # row 8: patient 2
    # row 9: blank separator
    grid = [
        _pad(["實際住院日"]),  # 1
        _pad([]),              # 2 blank
        _pad([]),              # 3
        _pad([]),              # 4
        _pad(["柯呈諭（2人）"]),  # 5
        _pad(["姓名", "病歷", "EMR", "摘要", "手動", "術前診斷", "預計心導管", "註記"]),  # 6
        _pad(["王小明", "12345678", "y", "sum", "", "CAD", "Left heart cath.", ""]),  # 7
        _pad(["李大華", "87654321", "y", "sum", "", "pAf", "RF ablation", "浩"]),  # 8
        _pad([]),  # 9 blank → end
    ]
    tables = os_.parse_subtables_grid(grid)
    assert list(tables.keys()) == ["柯呈諭"]
    pts = tables["柯呈諭"]
    assert len(pts) == 2
    assert pts[0]["name"] == "王小明"
    assert pts[0]["chart_no"] == "12345678"
    assert pts[0]["diagnosis"] == "CAD"
    assert pts[0]["cathlab"] == "Left heart cath."
    assert pts[0]["row"] == 7  # 1-based
    assert pts[1]["note"] == "浩"
    assert pts[1]["row"] == 8


def test_parse_multi_doctor_tables():
    grid = [
        _pad(["柯呈諭（1人）"]),            # 1
        _pad(["姓名", "病歷"]),             # 2
        _pad(["A", "1"]),                   # 3
        _pad([]),                           # 4 blank
        _pad(["陳儒逸（1人）"]),            # 5
        _pad(["姓名", "病歷"]),             # 6
        _pad(["B", "2"]),                   # 7
        _pad([]),                           # 8
    ]
    tables = os_.parse_subtables_grid(grid)
    assert set(tables.keys()) == {"柯呈諭", "陳儒逸"}
    assert tables["柯呈諭"][0]["row"] == 3
    assert tables["陳儒逸"][0]["row"] == 7


def test_parse_stops_on_blank_row():
    grid = [
        _pad(["柯呈諭（3人）"]),
        _pad(["姓名", "病歷"]),
        _pad(["A", "1"]),
        _pad([]),          # blank — stop before 2nd patient
        _pad(["B", "2"]),
    ]
    tables = os_.parse_subtables_grid(grid)
    assert len(tables["柯呈諭"]) == 1


def test_parse_empty_grid():
    assert os_.parse_subtables_grid([]) == {}


def test_parse_grid_without_any_titles():
    grid = [_pad(["實際住院日"]), _pad(["patient data"])]
    assert os_.parse_subtables_grid(grid) == {}
