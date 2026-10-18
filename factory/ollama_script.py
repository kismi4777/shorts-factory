"""Local Ollama script generation (not available on GitHub Actions)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b")
DEFAULT_BASE = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")


def _extract_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise RuntimeError("empty LLM response")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        raise RuntimeError(f"no JSON in LLM response: {raw[:200]}")
    return json.loads(m.group(0))


def chat_json(system: str, user: str, *, model: str = DEFAULT_MODEL, timeout: float = 90.0) -> dict[str, Any]:
    url = f"{DEFAULT_BASE}/api/chat"
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {"temperature": 0.7},
    }
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
    content = (data.get("message") or {}).get("content") or ""
    return _extract_json(content)


def generate_stock_script(topic: str, *, language: str = "ru") -> dict[str, Any]:
    system = (
        "You write short vertical video scripts. Reply with JSON only. "
        "No markdown. Keep spoken script under 90 words."
    )
    user = (
        f"Language: {language}\nTopic: {topic}\n\n"
        "Return JSON:\n"
        '{"script":"spoken narration 2-4 short paragraphs",'
        '"search_terms":["3-6 English stock-video keywords"],'
        '"title":"short title"}\n'
        "search_terms must be English for Pexels. script in the requested language."
    )
    data = chat_json(system, user)
    script = str(data.get("script") or "").strip()
    terms = data.get("search_terms") or data.get("video_terms") or []
    if isinstance(terms, str):
        terms = [t.strip() for t in re.split(r"[,;\n]", terms) if t.strip()]
    terms = [str(t).strip() for t in terms if str(t).strip()][:8]
    if not script:
        raise RuntimeError("stock script empty")
    if not terms:
        terms = [w for w in re.findall(r"[A-Za-z]{3,}", topic)][:4] or ["nature", "city"]
    return {
        "script": script,
        "search_terms": terms,
        "title": str(data.get("title") or topic)[:80],
    }


def generate_reddit_script(topic: str, *, language: str = "ru") -> dict[str, Any]:
    """ShortGPT-style story narration for gameplay background."""
    system = (
        "You write viral Reddit-style story shorts for voiceover over gameplay. "
        "JSON only. Spoken script under 110 words, first person or storyteller."
    )
    user = (
        f"Language: {language}\nTheme/prompt: {topic}\n\n"
        "Return JSON:\n"
        '{"script":"hook + story + twist, for voiceover",'
        '"title":"clickable title",'
        '"hook":"first sentence hook"}\n'
        "No hashtags. No stage directions."
    )
    data = chat_json(system, user)
    script = str(data.get("script") or "").strip()
    if not script:
        raise RuntimeError("reddit script empty")
    return {
        "script": script,
        "title": str(data.get("title") or topic)[:80],
        "hook": str(data.get("hook") or "")[:160],
        "search_terms": [],
    }
