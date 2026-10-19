"""Detect ready voiceover scripts and strip CapCut/Telegram scaffolding."""

from __future__ import annotations

import re

_SECTION = re.compile(
    r"^\s*(\[[^\]]+\]|"
    r"РАЗВИТИЕ|КУЛЬМИНАЦИЯ|РАЗВЯЗКА|ЗАКОЛЬЦОВКА|ХУК|ЗАВЯЗКА|"
    r"HOOK|CLIMAX|OUTRO|INTRO).*$",
    re.I | re.M,
)
_VOICE_BLOCK = re.compile(
    r"(?:Голос|Voice)\s*:\s*[«\"']?(.*?)(?=(?:\n\s*(?:\[|(?:Голос|Voice)\s*:))|$)",
    re.I | re.S,
)
_READY_HINT = re.compile(
    r"(Голос\s*:|Voice\s*:|\[\s*0:\d|РАЗВИТИЕ|КУЛЬМИНАЦИЯ|РАЗВЯЗКА|ЗАКОЛЬЦОВКА)",
    re.I,
)


def looks_like_ready_script(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _READY_HINT.search(t):
        return True
    # long paste ≈ finished narration
    return len(t) >= 280


def topic_slug(text: str) -> str:
    first = re.split(r"[.!?\n]", (text or "").strip(), maxsplit=1)[0].strip()
    words = re.findall(r"[A-Za-zА-Яа-яЁё0-9\-]+", first)
    return " ".join(words[:8]) or (text or "")[:60]


def extract_spoken_script(text: str) -> str:
    """Turn a structured CapCut/TG script into plain TTS narration."""
    raw = (text or "").strip()
    if not raw:
        return ""

    blocks = [m.group(1).strip() for m in _VOICE_BLOCK.finditer(raw) if m.group(1).strip()]
    if blocks:
        spoken = " ".join(blocks)
    else:
        cleaned_lines: list[str] = []
        for line in raw.splitlines():
            if _SECTION.match(line.strip()):
                continue
            if re.match(r"^\s*(?:Голос|Voice)\s*:", line, re.I):
                line = re.sub(r"^\s*(?:Голос|Voice)\s*:\s*", "", line, flags=re.I)
            cleaned_lines.append(line)
        spoken = " ".join(cleaned_lines)

    spoken = spoken.replace("«", "").replace("»", "").replace('"', "").replace("'", "")
    spoken = re.sub(r"\s+", " ", spoken).strip()
    # keep Shorts length sane for Edge-TTS + Actions
    if len(spoken) > 1200:
        spoken = spoken[:1200].rsplit(" ", 1)[0].strip()
    return spoken
