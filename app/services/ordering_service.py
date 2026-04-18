"""
Step 4 — Ordering.

After the user confirms F (術前診斷) and G (預計心導管) in each doctor
sub-table, we rebuild the N–W ordered list:
  N=序號  O=主治醫師  P=病人姓名  Q=備註(住服)  R=備註
  S=病歷號  T=術前診斷  U=預計心導管  V=每日續等清單  W=改期

This module just reads the sub-tables + existing N-row patient order and
repopulates T/U from sub-tables. Columns V (waitlist) and W (reschedule)
are preserved as they are manually edited.
"""
from __future__ import annotations

from . import sheet_service


def read_doctor_subtables(date: str) -> dict[str, list[dict]]:
    """
    Scan rows below main data for title cells like "李文煌（3人）"
    and harvest the 8-col sub-table following each.
    """
    ws = sheet_service.get_worksheet(date)
    if ws is None:
        raise ValueError(f"找不到工作表 {date}")
    grid = sheet_service.read_range(ws, "A1:H500")
    tables: dict[str, list[dict]] = {}
    i = 0
    while i < len(grid):
        row = grid[i]
        if row and row[0] and "人）" in row[0]:
            doctor = row[0].split("（")[0].strip()
            i += 2  # skip title + sub-header
            patients = []
            while i < len(grid):
                r = (grid[i] + [""] * 8)[:8]
                if not any(c.strip() for c in r):
                    break
                if "人）" in r[0]:
                    break
                patients.append({
                    "name":      r[0].strip(),
                    "chart_no":  r[1].strip(),
                    "emr":       r[2].strip(),
                    "summary":   r[3].strip(),
                    "manual":    r[4].strip(),
                    "diagnosis": r[5].strip(),
                    "cathlab":   r[6].strip(),
                    "note":      r[7].strip(),
                })
                i += 1
            tables[doctor] = patients
            continue
        i += 1
    return tables


def integrate_ordering(date: str) -> dict:
    """
    Merge sub-table F/G back into N-W ordered list by matching chart_no.
    Preserves V (waitlist) and W (reschedule) since those are manual flags.
    """
    ws = sheet_service.get_worksheet(date)
    existing = sheet_service.read_range(ws, "N2:W200")
    tables = read_doctor_subtables(date)

    # chart_no -> (diagnosis, cathlab, note)
    lookup = {}
    for _doc, pts in tables.items():
        for p in pts:
            if p["chart_no"]:
                lookup[p["chart_no"]] = p

    out: list[list[str]] = []
    for r in existing:
        r = (r + [""] * 10)[:10]
        if not r[2].strip():  # no patient name — stop
            break
        chart = r[5].strip()
        info = lookup.get(chart, {})
        out.append([
            r[0], r[1], r[2], r[3], r[4],
            r[5],
            info.get("diagnosis", r[6]),
            info.get("cathlab",   r[7]),
            r[8],   # V preserve
            r[9],   # W preserve
        ])

    if not out:
        return {"rows": 0}
    end_row = 1 + len(out)
    sheet_service.write_range(ws, f"N2:W{end_row}", out, raw=False)
    return {"rows": len(out), "range": f"N2:W{end_row}"}
