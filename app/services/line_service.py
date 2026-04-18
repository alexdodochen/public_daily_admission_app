"""
Step 6 — LINE 推播入院名單。

Build a text message from the date sheet's ordered N-Q columns
(序號 / 主治醫師 / 病人姓名 / 備註(住服)) and push it to the configured
LINE group via the Messaging API.

Per memory/feedback_admission_push_nq_only.md: 只傳 N-Q 四欄，不包含其他。
"""
from __future__ import annotations

import asyncio
import json
import urllib.request
from typing import Optional

from .. import config as appconfig
from . import sheet_service


LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


def build_message(date: str, ordered_rows: list[list[str]]) -> str:
    """
    Build a plain-text admission list. Each line:
        <序號>. <主治> <姓名>  [備註(住服)]
    """
    header = f"【{date[:4]}/{date[4:6]}/{date[6:8]} 入院名單】"
    body_lines: list[str] = []
    for r in ordered_rows:
        r = (r + ["", "", "", ""])[:4]
        seq, doctor, name, note = r
        if not name.strip():
            continue
        line = f"{seq}. {doctor} {name}"
        if note.strip():
            line += f"  [{note}]"
        body_lines.append(line)
    if not body_lines:
        return f"{header}\n(無病人)"
    return header + "\n" + "\n".join(body_lines)


def read_ordered_nq(date: str) -> list[list[str]]:
    """Read N-Q (序號/主治/姓名/備註(住服)) from the date sheet."""
    ws = sheet_service.get_worksheet(date)
    if ws is None:
        raise ValueError(f"找不到工作表 {date}")
    rows = sheet_service.read_range(ws, "N2:Q200")
    out = []
    for r in rows:
        r = (r + ["", "", "", ""])[:4]
        if not r[2].strip():
            break
        out.append(r)
    return out


def _push_sync(token: str, group_id: str, text: str) -> dict:
    payload = json.dumps({
        "to": group_id,
        "messages": [{"type": "text", "text": text[:4999]}],
    }).encode("utf-8")
    req = urllib.request.Request(
        LINE_PUSH_URL, data=payload, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {"status": resp.status, "body": resp.read().decode("utf-8", "ignore")}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "body": e.read().decode("utf-8", "ignore"), "error": True}


async def preview(date: str) -> str:
    rows = await asyncio.to_thread(read_ordered_nq, date)
    return build_message(date, rows)


async def push(date: str, override_group: str = "") -> dict:
    cfg = appconfig.load()
    if not cfg.line_token:
        raise RuntimeError("請先到「設定」頁填入 LINE channel access token")
    group = override_group.strip() or cfg.line_group_id
    if not group:
        raise RuntimeError("請填入 LINE group ID（設定頁或此面板）")

    rows = await asyncio.to_thread(read_ordered_nq, date)
    text = build_message(date, rows)
    result = await asyncio.to_thread(_push_sync, cfg.line_token, group, text)
    return {"sent_to": group, "length": len(text), "preview": text, **result}
