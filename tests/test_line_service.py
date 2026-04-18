"""Pure-logic tests for line_service.build_message."""
from __future__ import annotations

from app.services import line_service as ls


def test_message_header_formats_date():
    msg = ls.build_message("20260420", [["1", "柯呈諭", "王小明", ""]])
    assert msg.startswith("【2026/04/20 入院名單】")


def test_message_body_lines():
    rows = [
        ["1", "柯呈諭", "王小明", ""],
        ["2", "陳儒逸", "李大華", "同意書"],
    ]
    msg = ls.build_message("20260420", rows)
    lines = msg.splitlines()
    assert lines[1] == "1. 柯呈諭 王小明"
    assert lines[2] == "2. 陳儒逸 李大華  [同意書]"


def test_message_skips_blank_names():
    rows = [
        ["1", "柯呈諭", "王小明", ""],
        ["", "", "", ""],
        ["2", "陳儒逸", "", ""],  # missing name → skip
    ]
    msg = ls.build_message("20260420", rows)
    assert "李" not in msg
    # only one patient line
    assert msg.count("柯呈諭") == 1
    assert "陳儒逸" not in msg


def test_empty_list_message():
    msg = ls.build_message("20260420", [])
    assert "無病人" in msg


def test_short_rows_pad_safely():
    # Only 3 cols provided, no 備註
    msg = ls.build_message("20260420", [["1", "柯呈諭", "王小明"]])
    assert "1. 柯呈諭 王小明" in msg
    # no stray "[]"
    assert "[]" not in msg
