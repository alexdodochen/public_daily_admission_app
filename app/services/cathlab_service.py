"""
Step 5 — WEBCVIS 導管排程：驗證 + 規劃 + keyin（完整版）

本地版三個操作：
  - verify(admit_date): 跨比對子表格 vs WEBCVIS 排程，找出漏排/誤排
  - plan(admit_date):   列出該入院日的 keyin 計畫（時段 / 時間 / 房間 / 診斷 ID）
  - keyin(admit_date):  實際 ADD + UPT（Phase 1 新增、Phase 2 補 pdijson/phcjson）

規則來源：CLAUDE.md 第 1-9、17-18 條 + memory/feedback_cathlab_*。
靜態對應表放在 app/data/static/（id_maps, doctor_codes, schedule）。
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .. import config as appconfig
from . import sheet_service


SKIP_KEYWORDS = ["不排程", "檢查"]
ZHANG_BORROWED_BY = ["王思翰", "張倉惟"]  # 借用張獻元時段時的註記關鍵字
STATIC_DIR = Path(__file__).resolve().parent.parent / "data" / "static"

_id_maps: Optional[dict] = None
_doctor_codes: Optional[dict] = None
_schedule: Optional[dict] = None


# ---------------------------------- static loaders ----------------------------------

def _load_json(name: str) -> dict:
    path = STATIC_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def id_maps() -> dict:
    global _id_maps
    if _id_maps is None:
        _id_maps = _load_json("cathlab_id_maps.json")
    return _id_maps


def doctor_codes() -> dict:
    global _doctor_codes
    if _doctor_codes is None:
        _doctor_codes = _load_json("doctor_codes.json")
    return _doctor_codes


def schedule() -> dict:
    global _schedule
    if _schedule is None:
        _schedule = _load_json("cathlab_schedule.json")
    return _schedule


# ---------------------------------- cath date rule ----------------------------------

def get_cathlab_date(admit_date: str, doctor: str, note: str) -> str:
    """
    入院日 -> 導管日：
    - 週五入院 → 同日（週六無排程）
    - 張獻元週二入院 + 註記不含 王思翰/張倉惟 → 同日 PM（他週二自己時段）
    - 其他 → N+1
    """
    dt = datetime.strptime(admit_date, "%Y%m%d")
    wd = dt.weekday()
    if wd == 4:  # Friday
        cath = dt
    elif doctor == "張獻元" and wd == 1 and not any(k in note for k in ZHANG_BORROWED_BY):
        cath = dt
    else:
        cath = dt + timedelta(days=1)
    return cath.strftime("%Y/%m/%d")


# ---------------------------------- id / slot resolvers ----------------------------------

def _resolve_id(text: str, table: dict) -> tuple[str, str]:
    """
    Try exact, then suffix-after-">", then substring; return (resolved_label, id) or ("", "").
    """
    if not text:
        return "", ""
    t = text.strip()
    if t in table:
        return t, table[t]
    # "EP study/RFA > pAf" → try "pAf"
    if ">" in t:
        tail = t.rsplit(">", 1)[1].strip()
        if tail in table:
            return tail, table[tail]
    # substring (longest label that appears in t wins)
    best = ""
    for k in table:
        if k and k in t and len(k) > len(best):
            best = k
    if best:
        return best, table[best]
    return "", ""


def resolve_diag(text: str) -> tuple[str, str]:
    return _resolve_id(text, id_maps().get("diag", {}))


def resolve_proc(text: str) -> tuple[str, str]:
    return _resolve_id(text, id_maps().get("proc", {}))


def compute_slot(doctor: str, cath_date_str: str) -> dict:
    """
    Returns {session: AM|PM|OFF, room: H1/H2/C1/C2, in_schedule: bool}.
    OFF → 非時段（H1, 2100+）.
    """
    try:
        dt = datetime.strptime(cath_date_str, "%Y/%m/%d")
    except ValueError:
        return {"session": "OFF", "room": "H1", "in_schedule": False}
    wd = str(dt.weekday())   # 0..4
    info = schedule().get("doctors", {}).get(doctor, {})
    slot = info.get(wd)
    if slot:
        return {"session": slot["session"], "room": slot["room"], "in_schedule": True}
    return {"session": "OFF", "room": "H1", "in_schedule": False}


def compute_time(session: str, index: int) -> str:
    """AM starts 0600, PM starts 1800 (skip 1700 legacy), OFF starts 2100. +index minutes."""
    base = {"AM": 6 * 60, "PM": 18 * 60, "OFF": 21 * 60}.get(session, 21 * 60)
    minute = base + index
    return f"{minute // 60:02d}{minute % 60:02d}"


# ---------------------------------- patient reader ----------------------------------

def _read_w_markers(data: list[list[str]]) -> dict[str, str]:
    """N-W ordering 區塊的 W 欄（改期）— 回傳 {病歷號: W值}."""
    out = {}
    for row in data:
        if len(row) < 23:
            continue
        chart = (row[18] or "").strip()   # S = index 18
        w     = (row[22] or "").strip()   # W = index 22
        if chart and w and w != "改期":
            out[chart] = w
    return out


def read_patients(date: str) -> list[dict]:
    """Scan date sheet 子表格 + W-column skips. Returns patient dicts with
    fields: seq, doctor, name, chart, diag, cath, note, skip (bool)."""
    ws = sheet_service.get_worksheet(date)
    if not ws:
        raise ValueError(f"找不到工作表：{date}")
    data = ws.get_all_values()
    reschedules = _read_w_markers(data)

    patients: list[dict] = []
    current_doctor = ""
    seq = 0
    for row in data:
        r = (row[:8] + [""] * 8)[:8]
        col_a = r[0].strip()

        if "人）" in col_a:
            current_doctor = col_a.split("（")[0].strip()
            continue
        if col_a == "姓名":
            continue
        if col_a and r[1].strip() and current_doctor:
            seq += 1
            name = col_a
            chart = r[1].strip()
            note = r[7].strip()
            diag = r[5].strip()
            cath = r[6].strip()
            w_mark = reschedules.get(chart, "")
            should_skip = any(k in note for k in SKIP_KEYWORDS) or bool(w_mark)
            if w_mark:
                note = (note + f" [改期→{w_mark}]").strip()
            patients.append({
                "seq": seq, "doctor": current_doctor,
                "name": name, "chart": chart,
                "diag": diag, "cath": cath, "note": note,
                "skip": should_skip,
            })
    return patients


# ------------------------------ WEBCVIS queries ------------------------------

async def _login(page, cfg) -> None:
    base_host = cfg.cathlab_base_url.rsplit("/WEBCVIS", 1)[0] + "/WEBCVIS"
    await page.goto(base_host + "/")
    await page.wait_for_load_state("networkidle", timeout=15000)
    await page.fill('input[name="userid"]', cfg.cathlab_user)
    await page.fill('input[name="password"]', cfg.cathlab_pass)
    await page.click('input[type="submit"], button[type="submit"]')
    await page.wait_for_load_state("networkidle", timeout=10000)


async def _set_date_and_query(page, base_url: str, date_str: str) -> None:
    await page.goto(base_url)
    await page.wait_for_load_state("networkidle", timeout=10000)
    await asyncio.sleep(1)
    await page.evaluate(f"""() => {{
        let a = document.getElementById("daySelect1");
        let b = document.getElementById("daySelect2");
        if(a){{a.removeAttribute("readonly"); a.value = "{date_str}";}}
        if(b){{b.removeAttribute("readonly"); b.value = "{date_str}";}}
    }}""")
    await asyncio.sleep(0.3)
    await page.evaluate("""() => {
        if (document.HCO1WForm) {
            document.HCO1WForm.buttonName.name = "QRY";
            document.HCO1WForm.buttonName.value = "QRY";
            document.HCO1WForm.submit();
        }
    }""")
    await page.wait_for_load_state("networkidle", timeout=10000)
    await asyncio.sleep(1)


async def _get_existing_charts(page) -> set[str]:
    charts = await page.evaluate(r"""() => {
        let c = [];
        document.querySelectorAll("#row tr").forEach(r => {
            let el = r.querySelector("#hes_patno");
            if (el && el.value) c.push(el.value.trim());
        });
        if (c.length === 0) {
            document.querySelectorAll("#row td").forEach(td => {
                let t = td.textContent.trim();
                if (/^\d{7,8}$/.test(t)) c.push(t);
            });
        }
        return c;
    }""")
    return set(charts)


async def _login_and_query(dates: list[str]) -> dict[str, set[str]]:
    """Return {cath_date: set(chart_no)} using the user's WEBCVIS creds."""
    cfg = appconfig.load()
    if not cfg.cathlab_base_url or not cfg.cathlab_user or not cfg.cathlab_pass:
        raise RuntimeError("請先在設定頁填入 WEBCVIS URL / 帳號 / 密碼")

    from playwright.async_api import async_playwright

    results: dict[str, set[str]] = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=100)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await ctx.new_page()
        try:
            await _login(page, cfg)
            for d in dates:
                await _set_date_and_query(page, cfg.cathlab_base_url, d)
                results[d] = await _get_existing_charts(page)
        finally:
            await browser.close()
    return results


# --------------------------------- plan enrichment ---------------------------------

def _enrich(patients: list[dict], admit_date: str) -> list[dict]:
    """Attach cath_date / session / room / time / diag_id / proc_id / note_fallback to each patient."""
    # Group by (cath_date, doctor) to number patients per doctor block
    counters: dict[tuple[str, str], int] = {}
    for p in patients:
        if p["skip"]:
            p["cath_date"] = ""
            p["session"] = ""
            p["room"] = ""
            p["time"] = ""
            p["diag_id"] = ""
            p["diag_label"] = ""
            p["proc_id"] = ""
            p["proc_label"] = ""
            p["note_out"] = p["note"]
            continue
        cath = get_cathlab_date(admit_date, p["doctor"], p["note"])
        slot = compute_slot(p["doctor"], cath)
        key = (cath, p["doctor"])
        idx = counters.get(key, 0)
        counters[key] = idx + 1
        time_s = compute_time(slot["session"], idx)
        d_label, d_id = resolve_diag(p["diag"])
        q_label, q_id = resolve_proc(p["cath"])
        note_out = p["note"]
        # Non-schedule → 備註加「本日無時段」
        if not slot["in_schedule"] and "本日無時段" not in note_out:
            note_out = (note_out + " 本日無時段").strip()
        # Procedure 文字沒映射 → 塞備註（CLAUDE.md 規則 feedback_cathlab_note_fallback）
        if p["cath"] and not q_id and p["cath"] not in note_out:
            note_out = (note_out + " " + p["cath"]).strip()
        p["cath_date"] = cath
        p["session"] = slot["session"]
        p["room"] = slot["room"]
        p["time"] = time_s
        p["diag_id"] = d_id
        p["diag_label"] = d_label
        p["proc_id"] = q_id
        p["proc_label"] = q_label
        p["note_out"] = note_out
    return patients


# --------------------------------- high-level ---------------------------------

async def verify(admit_date: str) -> dict:
    """Returns a report: per-patient OK / MISSING / SKIP."""
    patients = _enrich(read_patients(admit_date), admit_date)
    to_check = [p for p in patients if not p["skip"]]
    skipped  = [p for p in patients if p["skip"]]

    unique_dates = sorted({p["cath_date"] for p in to_check})
    webcvis = await _login_and_query(unique_dates) if unique_dates else {}

    found, missing = [], []
    for p in to_check:
        charts = webcvis.get(p["cath_date"], set())
        (found if p["chart"] in charts else missing).append(p)

    all_charts: set[str] = set()
    for s in webcvis.values():
        all_charts |= s

    return {
        "admit_date": admit_date,
        "dates_queried": unique_dates,
        "found":   found,
        "missing": missing,
        "skipped": [
            {**p, "unexpected_present": p["chart"] in all_charts}
            for p in skipped
        ],
        "totals": {
            "ok": len(found), "missing": len(missing), "skip": len(skipped),
        },
    }


def plan(admit_date: str) -> dict:
    """
    Dry-run: list what would be keyed in, grouped by cath_date.
    Safe to run anytime — reads sub-tables + static data only.
    """
    patients = _enrich(read_patients(admit_date), admit_date)
    buckets: dict[str, list[dict]] = {}
    for p in patients:
        if p["skip"]:
            continue
        buckets.setdefault(p["cath_date"], []).append(p)
    return {
        "admit_date": admit_date,
        "plan": buckets,
        "skipped": [p for p in patients if p["skip"]],
    }


# --------------------------------- keyin (real ADD + UPT) ---------------------------------

def _build_json(label: str, item_id: str) -> str:
    if not item_id:
        return ""
    return json.dumps([{"name": label, "id": item_id}], ensure_ascii=False)


async def _add_patient(page, base_url: str, cath_date: str, p: dict) -> dict:
    chart = p["chart"]
    codes = doctor_codes()
    doc_code = codes["doctors"].get(p["doctor"], "")
    room_code = codes["rooms"].get(p["room"], "")
    if not doc_code:
        return {"chart": chart, "name": p["name"], "result": "error",
                "reason": f"主治醫師代碼未知：{p['doctor']}"}
    if not room_code:
        return {"chart": chart, "name": p["name"], "result": "error",
                "reason": f"房間代碼未知：{p['room']}"}

    diag_json = _build_json(p["diag_label"], p["diag_id"])
    proc_json = _build_json(p["proc_label"], p["proc_id"])
    note = p.get("note_out") or ""

    try:
        await page.click('input[name="patno2"]')
        await asyncio.sleep(0.4)
        await page.fill('input[name="patno2"]', chart)
        await asyncio.sleep(0.3)
        await page.press('input[name="patno2"]', "Enter")
        await asyncio.sleep(2)

        await page.evaluate(f"""() => {{
            document.querySelector('input[name="inspectiondate"]').value = "{cath_date}";
        }}""")
        await page.fill('input[name="inspectiontime"]', p["time"])
        await page.select_option('select[name="examroom"]', value=room_code)
        await page.select_option('select[name="attendingdoctor1"]', value=doc_code)
        # NOTE: second attending doctor handling omitted — user sets via 備註 per
        # CLAUDE.md rule 16 (葉立浩優先 otherwise go 備註)

        await page.evaluate(
            """([dj, pj]) => {
                if (dj) document.querySelector('[name="pdijson"]').value = dj;
                if (pj) document.querySelector('[name="phcjson"]').value = pj;
            }""",
            [diag_json, proc_json],
        )

        if note:
            await page.fill('input[name="note"]', note)

        await asyncio.sleep(0.3)
        await page.evaluate("""() => {
            document.HCO1WForm.buttonName.name = "ADD";
            document.HCO1WForm.buttonName.value = "ADD";
            document.HCO1WForm.submit();
        }""")
        await page.wait_for_load_state("networkidle", timeout=15000)
        await asyncio.sleep(1)
        return {"chart": chart, "name": p["name"], "result": "ok"}
    except Exception as e:
        return {"chart": chart, "name": p["name"], "result": "error", "reason": str(e)}


async def _upt_patient(page, p: dict) -> dict:
    """Re-open the row by chart and force pdijson/phcjson via UPT."""
    chart = p["chart"]
    if not (p["diag_id"] or p["proc_id"]):
        return {"chart": chart, "name": p["name"], "result": "skip",
                "reason": "no id to fix"}
    diag_json = _build_json(p["diag_label"], p["diag_id"])
    proc_json = _build_json(p["proc_label"], p["proc_id"])

    found = await page.evaluate(
        """(chart) => {
            let rows = document.querySelectorAll("#row tr");
            for (let row of rows) {
                let el = row.querySelector("#hes_patno");
                if (el && el.value === chart) { row.click(); return true; }
            }
            return false;
        }""",
        chart,
    )
    if not found:
        return {"chart": chart, "name": p["name"], "result": "error",
                "reason": "row not found on page"}

    await asyncio.sleep(0.5)
    await page.evaluate(
        """([dj, pj, dt, pt]) => {
            if (dj) {
                document.querySelector('[name="pdijson"]').value = dj;
                let f = document.querySelector('[name="prediagnosisitem"]');
                if (f) f.value = dt;
            }
            if (pj) {
                document.querySelector('[name="phcjson"]').value = pj;
                let f = document.querySelector('[name="preheartcatheter"]');
                if (f) f.value = pt;
            }
        }""",
        [diag_json, proc_json, p["diag_label"], p["proc_label"]],
    )
    await asyncio.sleep(0.3)
    await page.evaluate("""() => {
        document.HCO1WForm.buttonName.name = "UPT";
        document.HCO1WForm.buttonName.value = "UPT";
        document.HCO1WForm.submit();
    }""")
    await page.wait_for_load_state("networkidle", timeout=15000)
    await asyncio.sleep(1)
    return {"chart": chart, "name": p["name"], "result": "ok"}


async def keyin(admit_date: str, dry_run: bool = False) -> dict:
    """
    Real WEBCVIS ADD + UPT for all non-skipped patients.
    dry_run=True → returns the plan without launching a browser.
    """
    cfg = appconfig.load()
    if not dry_run:
        if not cfg.cathlab_base_url or not cfg.cathlab_user or not cfg.cathlab_pass:
            raise RuntimeError("請先在設定頁填入 WEBCVIS URL / 帳號 / 密碼")

    patients = _enrich(read_patients(admit_date), admit_date)
    active = [p for p in patients if not p["skip"]]
    skipped = [p for p in patients if p["skip"]]

    if dry_run or not active:
        return {
            "admit_date": admit_date,
            "dry_run": True,
            "would_add": active,
            "skipped": skipped,
        }

    from playwright.async_api import async_playwright

    log: list[str] = []
    add_results: list[dict] = []
    upt_results: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=150)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await ctx.new_page()
        try:
            await _login(page, cfg)
            log.append("登入成功")

            unique_dates = sorted({p["cath_date"] for p in active})
            # Pre-fetch existing charts per date to skip duplicates
            existing: dict[str, set[str]] = {}
            for d in unique_dates:
                await _set_date_and_query(page, cfg.cathlab_base_url, d)
                existing[d] = await _get_existing_charts(page)
                log.append(f"查詢 {d}：現有 {len(existing[d])} 筆")

            # Phase 1: ADD
            log.append("--- Phase 1: ADD ---")
            for i, p in enumerate(active):
                d = p["cath_date"]
                if p["chart"] in existing[d]:
                    add_results.append({"chart": p["chart"], "name": p["name"],
                                        "result": "skip", "reason": "already exists"})
                    continue
                if i > 0:
                    await _set_date_and_query(page, cfg.cathlab_base_url, d)
                r = await _add_patient(page, cfg.cathlab_base_url, d, p)
                add_results.append(r)

            # Phase 2: UPT (pdijson / phcjson)
            log.append("--- Phase 2: UPT ---")
            for p in active:
                if not (p["diag_id"] or p["proc_id"]):
                    continue
                await _set_date_and_query(page, cfg.cathlab_base_url, p["cath_date"])
                r = await _upt_patient(page, p)
                upt_results.append(r)

            # Final verification
            final: dict[str, set[str]] = {}
            for d in unique_dates:
                await _set_date_and_query(page, cfg.cathlab_base_url, d)
                final[d] = await _get_existing_charts(page)
        finally:
            await browser.close()

    summary = {
        "ok": sum(1 for r in add_results if r["result"] == "ok"),
        "skip": sum(1 for r in add_results if r["result"] == "skip"),
        "error": sum(1 for r in add_results if r["result"] == "error"),
    }
    missing_after = [
        {"chart": p["chart"], "name": p["name"], "cath_date": p["cath_date"]}
        for p in active if p["chart"] not in final.get(p["cath_date"], set())
    ]

    return {
        "admit_date": admit_date,
        "add": add_results,
        "upt": upt_results,
        "summary": summary,
        "missing_after": missing_after,
        "skipped": skipped,
        "log": log,
        "implemented": True,
    }
