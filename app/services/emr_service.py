"""
Step 3 — EMR extraction.

Strategy: user manually logs in to their EMR system in a browser, copies the
session URL, and pastes it into the UI. We drive Playwright with that URL so
the session cookie is already valid (per feedback_emr_manual_login memory).

For each patient we:
  1. Load the EMR query page using the user's session URL
  2. Navigate to the patient's chart / a recent visit of the chart
  3. Dump the visible SOAP-note HTML
  4. Ask the LLM to produce a 4-section summary:
        主訴 / 病史 / 理學檢查 / 檢查結果
  5. Return summary + raw-html for review

Because every hospital's EMR differs, this module exposes a generic
`fetch_raw_html(session_url, chart_no)` hook. The default impl works with
the NCKUH EMR URL pattern used in the reference repo — other users should
override via config or subclass.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from ..llm import get_llm

SUMMARY_PROMPT = """你是心臟內科住院醫師。請把下方 EMR SOAP note HTML 整理成繁體中文 4 段摘要：

1. 主訴：一句話描述主要問題與入院原因
2. 病史：CAD/HTN/DM/CKD 等慢性病 + 過去重要手術/導管紀錄
3. 理學檢查：BP、HR、心音、雜音、肺部、下肢水腫等
4. 檢查結果：EKG、Echo、Troponin、NT-proBNP、Cath、CT 等關鍵數值

規則：
- 每段 1–3 行，濃縮為要點，不要抄原文
- 抓不到就寫「—」
- 只輸出這 4 段純文字，不要 markdown heading 以外的裝飾
- 格式：
主訴：...
病史：...
理學檢查：...
檢查結果：...

EMR HTML：
"""


async def fetch_raw_html(page, session_url: str, chart_no: str) -> str:
    """
    Load the EMR, query by chart number, return visible SOAP HTML.
    This is a best-effort default; customize per hospital in production.
    """
    await page.goto(session_url, wait_until="networkidle")
    # Try to focus chart-number input; fall back to JS if selector missing
    try:
        await page.fill("input[name='chartno']", chart_no, timeout=3000)
        await page.press("input[name='chartno']", "Enter")
        await page.wait_for_load_state("networkidle")
    except Exception:
        pass

    # Prefer div.small blocks that actually hold SOAP notes
    html = await page.evaluate("""
        () => {
            const blocks = document.querySelectorAll('div.small');
            if (!blocks.length) return document.body.innerText;
            return Array.from(blocks).map(b => b.innerText).join('\\n---\\n');
        }
    """)
    return html or ""


async def summarize_html(html: str) -> str:
    if not html.strip():
        return "主訴：—\n病史：—\n理學檢查：—\n檢查結果：—"
    llm = get_llm()
    prompt = SUMMARY_PROMPT + html[:15000]
    return (await llm.text(prompt)).strip()


async def extract_patients(session_url: str,
                           patients: list[dict]) -> list[dict]:
    """
    For each {chart_no, name, doctor} fetch SOAP HTML + LLM summary.
    Returns list of {chart_no, name, doctor, html, summary}.
    """
    from playwright.async_api import async_playwright

    results: list[dict] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        try:
            for p in patients:
                try:
                    html = await fetch_raw_html(page, session_url, p["chart_no"])
                    summary = await summarize_html(html)
                    results.append({
                        **p, "html": html[:20000], "summary": summary, "error": ""
                    })
                except Exception as e:
                    results.append({**p, "html": "", "summary": "", "error": str(e)})
        finally:
            await browser.close()
    return results
