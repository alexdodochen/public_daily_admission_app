"""
Step 5 — WEBCVIS 導管排程：驗證 + 規劃 + keyin

本地版目前提供三種操作：
  - verify(admit_date): 跨比對子表格 vs WEBCVIS 排程，找出漏排/誤排
  - plan(admit_date):   列出該入院日的 keyin 計畫（誰、哪天、時段）
  - keyin(admit_date):  實際 ADD（目前為「標記為待實作」佔位；
                        請仍以 repo 的 per-date 腳本執行真正寫入）

規則來源：CLAUDE.md 第 1-9、17-18 條 + memory/feedback_cathlab_*。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from .. import config as appconfig
from . import sheet_service


SKIP_KEYWORDS = ["不排程", "檢查"]
ZHANG_BORROWED_BY = ["王思翰", "張倉惟"]  # 借用張獻元時段時的註記關鍵字


# ---------------------------------- helpers ----------------------------------

def get_cathlab_date(admit_date: str, doctor: str, note: str) -> str:
    """
    入院日 -> 導管日：
    - 週五入院 → 同日（週六無排程）
    - 張獻元週二入院 + 註記不含 王思翰/張倉惟 → 同日 PM（他週二自己時段）
    - 週日入院但詹世鴻 → 週一（詹非週五時段不動）
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
            # login
            base_host = cfg.cathlab_base_url.rsplit("/WEBCVIS", 1)[0] + "/WEBCVIS"
            await page.goto(base_host + "/")
            await page.wait_for_load_state("networkidle", timeout=15000)
            await page.fill('input[name="userid"]', cfg.cathlab_user)
            await page.fill('input[name="password"]', cfg.cathlab_pass)
            await page.click('input[type="submit"], button[type="submit"]')
            await page.wait_for_load_state("networkidle", timeout=10000)

            for d in dates:
                await page.goto(cfg.cathlab_base_url)
                await page.wait_for_load_state("networkidle", timeout=10000)
                await asyncio.sleep(1)
                await page.evaluate(f"""() => {{
                    let a = document.getElementById("daySelect1");
                    let b = document.getElementById("daySelect2");
                    if(a){{a.removeAttribute("readonly"); a.value = "{d}";}}
                    if(b){{b.removeAttribute("readonly"); b.value = "{d}";}}
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
                charts = await page.evaluate("""() => {
                    let c = [];
                    document.querySelectorAll("#row tr").forEach(r => {
                        let el = r.querySelector("#hes_patno");
                        if (el && el.value) c.push(el.value.trim());
                    });
                    if (c.length === 0) {
                        document.querySelectorAll("#row td").forEach(td => {
                            let t = td.textContent.trim();
                            if (/^\\d{7,8}$/.test(t)) c.push(t);
                        });
                    }
                    return c;
                }""")
                results[d] = set(charts)
        finally:
            await browser.close()
    return results


# --------------------------------- high-level ---------------------------------

async def verify(admit_date: str) -> dict:
    """Returns a report: per-patient OK / MISSING / SKIP."""
    patients = read_patients(admit_date)
    to_check = [p for p in patients if not p["skip"]]
    skipped  = [p for p in patients if p["skip"]]

    for p in to_check:
        p["cath_date"] = get_cathlab_date(admit_date, p["doctor"], p["note"])

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
    This doesn't touch WEBCVIS — safe to run anytime.
    """
    patients = read_patients(admit_date)
    for p in patients:
        p["cath_date"] = (
            get_cathlab_date(admit_date, p["doctor"], p["note"])
            if not p["skip"] else ""
        )
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


async def keyin(admit_date: str) -> dict:
    """
    實際 ADD 目前為佔位實作 —— 需要主治醫師時段表的 AM/PM/非時段規則，
    以及 PDI/PHC 對應（cathlab_id_maps.json）。請在下次 session 完成。
    暫時請使用 repo 舊的 per-date keyin 腳本。
    """
    return {
        "implemented": False,
        "reason": "真正的 ADD 需要再 port 時段表解析 + PDI/PHC 對應。"
                  "目前請用 repo 的 cathlab_keyin_*.py 執行；此面板先用 verify 確認結果。",
        "next_steps": [
            "1. 載入主治醫師導管時段表 → {doctor: {'Mon-Fri': 'AM'|'PM'|None}}",
            "2. 載入 cathlab_id_maps.json 做 diag/proc 文字 → PDI/PHC 對應",
            "3. 為每位 patient 決定時間槽（AM 0600+, PM 1800+, 非時段 2100+）",
            "4. Playwright 登入 → 逐筆 ADD（jQuery SaveButton.click）",
            "5. Phase 2 以 UPT 修正 pdijson / phcjson",
        ],
    }
