"""
Local user config — JSON-backed settings stored under app/data/.

Each user runs the app on their own machine and fills in:
  - which LLM provider (anthropic / openai / gemini)
  - their API key for that provider
  - path to their Google service-account JSON
  - their target Google Sheet ID
  - (optional) EMR base URL, WEBCVIS base URL, LINE push tokens

Nothing is shipped with the app. First-run => settings page.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
CONFIG_PATH = DATA_DIR / "config.json"


@dataclass
class AppConfig:
    # LLM
    llm_provider: str = ""          # "anthropic" | "openai" | "gemini"
    llm_api_key: str = ""
    llm_model: str = ""             # optional override; each provider has a default

    # Google Sheets
    google_creds_path: str = ""     # absolute path to service-account JSON
    sheet_id: str = ""

    # EMR (optional — only needed for Step 3)
    emr_base_url: str = "http://hisweb.hosp.ncku/Emrquery/"

    # WEBCVIS cathlab (optional — only needed for Step 5)
    cathlab_base_url: str = "http://cardiopacs01.hosp.ncku:8080/WEBCVIS/HCO/HCO1W001.do"
    cathlab_user: str = ""
    cathlab_pass: str = ""

    # LINE push (optional — only needed for Step 6)
    line_token: str = ""
    line_group_id: str = ""

    def is_ready(self) -> bool:
        """True if minimum settings for Step 1–2 are present."""
        return bool(self.llm_provider and self.llm_api_key
                    and self.google_creds_path and self.sheet_id)


_cached: Optional[AppConfig] = None


def load() -> AppConfig:
    global _cached
    if _cached is not None:
        return _cached
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            _cached = AppConfig(**{k: v for k, v in data.items()
                                   if k in AppConfig.__dataclass_fields__})
            return _cached
        except Exception:
            pass
    _cached = AppConfig()
    return _cached


def save(cfg: AppConfig) -> None:
    global _cached
    _cached = cfg
    CONFIG_PATH.write_text(
        json.dumps(asdict(cfg), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def update(**kwargs) -> AppConfig:
    cfg = load()
    for k, v in kwargs.items():
        if k in AppConfig.__dataclass_fields__ and v is not None:
            setattr(cfg, k, v)
    save(cfg)
    return cfg
