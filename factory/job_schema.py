"""Unified job JSON for local Ollama + GitHub Actions render."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

Mode = Literal["stock", "reddit_gameplay"]

ROOT = Path(__file__).resolve().parents[1]
JOBS_DIR = ROOT / "jobs"
OUT_DIR = ROOT / "output"


@dataclass
class ShortJob:
    id: str
    mode: Mode
    topic: str
    language: str = "ru"
    script: str = ""
    search_terms: list[str] = field(default_factory=list)
    voice: str = "ru-RU-SvetlanaNeural"
    aspect: str = "9:16"
    width: int = 1080
    height: int = 1920
    background: str = ""  # relative path under assets/backgrounds for reddit
    bgm: str = ""
    subtitle_style: str = "popup"
    created_at: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ShortJob":
        known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        payload = {k: v for k, v in data.items() if k in known}
        return cls(**payload)


def new_job_id(topic: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ]+", "-", topic.strip().lower())[:40].strip("-")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{slug or 'short'}-{uuid.uuid4().hex[:6]}"


def save_job(job: ShortJob, path: Optional[Path] = None) -> Path:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    if not job.created_at:
        job.created_at = datetime.now(timezone.utc).isoformat()
    out = path or (JOBS_DIR / f"{job.id}.json")
    out.write_text(json.dumps(job.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def load_job(path: Path | str) -> ShortJob:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    return ShortJob.from_dict(data)
