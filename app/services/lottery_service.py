"""
Step 2 — Lottery + Round-Robin.

- Reads 主治醫師抽籤表 to know each doctor's 籤數 (lottery tickets) for the day
- Randomly draws patients per doctor up to their ticket count
- Non-schedule doctors go last
- Produces a round-robin order: A1→B1→C1→A2→B2→...
- Writes N–P (序號 / 主治醫師 / 病人姓名) to the date sheet
"""
from __future__ import annotations

import random
from typing import Optional

from . import sheet_service


def read_main_patients(date: str) -> list[dict]:
    ws = sheet_service.get_worksheet(date)
    if ws is None:
        raise ValueError(f"找不到工作表 {date}，請先完成 Step 1")
    rows = sheet_service.read_range(ws, "A2:L200")
    out = []
    for i, r in enumerate(rows):
        # pad
        r = (r + [""] * 12)[:12]
        if not r[5].strip():  # no name → stop
            break
        out.append({
            "row": i + 2,
            "doctor": r[3].strip(),
            "name": r[5].strip(),
            "chart_no": r[8].strip(),
        })
    return out


def read_lottery_tickets(schedule_day: str) -> dict[str, int]:
    """
    Read 主治醫師抽籤表. Expected layout: first column = weekday label
    (週一/週二/...), subsequent columns = doctor names with header row
    listing tickets, or inline count annotations like "柯呈諭*2".

    This is a best-effort parser matching how the existing workflow stores
    it; callers can override the result in the UI.
    """
    ws = sheet_service.get_worksheet("主治醫師抽籤表")
    if ws is None:
        return {}
    rows = sheet_service.read_range(ws, "A1:Z50")
    tickets: dict[str, int] = {}
    day_label = schedule_day  # "週一".."週五"
    for r in rows:
        if not r:
            continue
        if r[0].strip() == day_label:
            for cell in r[1:]:
                if not cell.strip():
                    continue
                name = cell.strip()
                count = 1
                if "*" in name:
                    name, c = name.split("*", 1)
                    try:
                        count = int(c)
                    except ValueError:
                        count = 1
                tickets[name.strip()] = tickets.get(name.strip(), 0) + count
            break
    return tickets


def draw(patients: list[dict], tickets: dict[str, int],
         seed: Optional[int] = None) -> dict[str, list[dict]]:
    """
    Randomly pick patients for each doctor up to their ticket count.
    Patients whose doctor is not in `tickets` are treated as non-schedule.
    Returns {doctor: [patient, ...]} preserving doctor listing order in
    `tickets`, with non-schedule doctors appended at the end.
    """
    rng = random.Random(seed)
    by_doctor: dict[str, list[dict]] = {}
    for p in patients:
        by_doctor.setdefault(p["doctor"], []).append(p)

    result: dict[str, list[dict]] = {}
    # In-schedule doctors first
    for doc in tickets:
        pool = list(by_doctor.get(doc, []))
        rng.shuffle(pool)
        result[doc] = pool[: tickets.get(doc, len(pool))]

    # Non-schedule doctors (Friday special: 詹世鴻 too)
    for doc, pool in by_doctor.items():
        if doc not in tickets and doc:
            result[doc] = list(pool)
    return result


def round_robin(draws: dict[str, list[dict]],
                tickets: dict[str, int]) -> list[dict]:
    """True round-robin: take 1 from each doctor in turn until all empty."""
    # Order doctors: tickets dict first (insertion order), then non-schedule
    order: list[str] = []
    for d in tickets:
        if d in draws:
            order.append(d)
    for d in draws:
        if d not in order:
            order.append(d)

    queues = {d: list(ps) for d, ps in draws.items()}
    out: list[dict] = []
    while any(queues[d] for d in order):
        for d in order:
            if queues[d]:
                out.append({**queues[d].pop(0), "doctor": d})
    return out


def write_to_sheet(date: str, ordered: list[dict]) -> dict:
    """Write 序號/主治醫師/病人姓名/(空 Q)/(空 R)/病歷號 to N2:S{n+1}."""
    ws = sheet_service.get_worksheet(date)
    body = []
    for i, p in enumerate(ordered, start=1):
        body.append([str(i), p["doctor"], p["name"], "", "", p.get("chart_no", "")])
    end_row = 1 + len(body)
    sheet_service.write_range(ws, f"N2:S{end_row}", body, raw=False)
    return {"rows": len(body), "range": f"N2:S{end_row}"}
