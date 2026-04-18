"""
Step 1 — Image OCR.
LLM vision reads a hospital admission-list screenshot and returns structured rows.
Output columns match the date sheet's main data layout (A-L).
"""
from __future__ import annotations

from typing import Optional

from ..llm import get_llm, extract_json
from . import sheet_service

OCR_PROMPT = """你是醫療排程助理。請把這張住院名單截圖轉成 JSON 陣列。

每一列代表一位病人，欄位必須是這 12 個（缺的填空字串）：
  "admit_date"    實際住院日 (YYYY/MM/DD 或 MM/DD)
  "op_date"       開刀日 / 手術日（沒有填空字串）
  "department"    科別（常見：心內、CV）
  "doctor"        主治醫師（中文全名，例如「李文煌」）
  "icd_diagnosis" 主診斷 ICD（例如「I25.10 Atherosclerotic heart disease」）
  "name"          病人姓名（中文全名）
  "gender"        性別（男/女）
  "age"           年齡（數字）
  "chart_no"      病歷號碼（純數字字串，保留前導 0）
  "bed"           病床號
  "hint"          入院提示
  "urgent"        住急（有/無 或 空字串）

注意：
- 病歷號一定是數字字串，不要加斜線或空白。
- 若某欄模糊不確定，寫入你的最佳猜測並在欄位值後加「?」。
- 只輸出 JSON 陣列，不要其他文字。
"""


async def ocr_image(image_bytes: bytes, mime: str = "image/png") -> list[dict]:
    """Return list of patient dicts parsed from the screenshot."""
    llm = get_llm()
    raw = await llm.vision(image_bytes, OCR_PROMPT, mime=mime)
    data = extract_json(raw)
    if not isinstance(data, list):
        raise ValueError(f"LLM 未返回陣列。原始輸出前 500 字：\n{raw[:500]}")
    # Normalize keys / coerce types
    out = []
    for row in data:
        if not isinstance(row, dict):
            continue
        out.append({
            "admit_date":    str(row.get("admit_date", "")).strip(),
            "op_date":       str(row.get("op_date", "")).strip(),
            "department":    str(row.get("department", "")).strip(),
            "doctor":        str(row.get("doctor", "")).strip(),
            "icd_diagnosis": str(row.get("icd_diagnosis", "")).strip(),
            "name":          str(row.get("name", "")).strip(),
            "gender":        str(row.get("gender", "")).strip(),
            "age":           str(row.get("age", "")).strip(),
            "chart_no":      str(row.get("chart_no", "")).strip(),
            "bed":           str(row.get("bed", "")).strip(),
            "hint":          str(row.get("hint", "")).strip(),
            "urgent":        str(row.get("urgent", "")).strip(),
        })
    return out


def write_to_sheet(date: str, patients: list[dict]) -> dict:
    """Overwrite main data area A2:L{n+1} with reviewed patient rows."""
    ws = sheet_service.ensure_date_sheet(date)
    if not patients:
        return {"rows": 0, "sheet": date}

    body = []
    for p in patients:
        body.append([
            p.get("admit_date", ""), p.get("op_date", ""),
            p.get("department", ""), p.get("doctor", ""),
            p.get("icd_diagnosis", ""), p.get("name", ""),
            p.get("gender", ""), p.get("age", ""),
            p.get("chart_no", ""), p.get("bed", ""),
            p.get("hint", ""), p.get("urgent", ""),
        ])
    end_row = 1 + len(body)
    sheet_service.write_range(ws, f"A2:L{end_row}", body, raw=False)
    return {"rows": len(body), "sheet": date, "range": f"A2:L{end_row}"}
