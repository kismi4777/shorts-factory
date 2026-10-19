"""Edge-TTS voiceover + approximate word timings for popup subs."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any


async def _synth(
    text: str,
    voice: str,
    mp3_path: Path,
    *,
    rate: str = "-8%",
    pitch: str = "+0Hz",
) -> list[dict[str, Any]]:
    import edge_tts

    # slower rate = clearer RU narration (Edge free voices still robotic)
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    words: list[dict[str, Any]] = []
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    with open(mp3_path, "wb") as f:
        async for chunk in communicate.stream():
            kind = chunk.get("type")
            if kind == "audio":
                f.write(chunk["data"])
            elif kind == "WordBoundary":
                # offset/duration in 100-ns units
                words.append(
                    {
                        "text": chunk.get("text") or "",
                        "start": float(chunk.get("offset", 0)) / 10_000_000,
                        "duration": float(chunk.get("duration", 0)) / 10_000_000,
                    }
                )
    return words


def synthesize(text: str, voice: str, mp3_path: Path) -> list[dict[str, Any]]:
    clean = re.sub(r"\s+", " ", (text or "").strip())
    # strip leftover quote titles that confuse TTS
    clean = re.sub(r"^[«\"].*?[»\"]\s*", "", clean).strip() or clean
    if not clean:
        raise RuntimeError("empty TTS text")
    return asyncio.run(_synth(clean, voice, mp3_path))


def words_to_ass(words: list[dict[str, Any]], *, width: int = 1080, height: int = 1920) -> str:
    """Simple pop-up ASS: one word at a time, bottom center."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Pop,Arial Black,72,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,0,2,40,40,220,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for w in words:
        text = (w.get("text") or "").strip()
        if not text:
            continue
        start = float(w.get("start") or 0)
        end = start + max(float(w.get("duration") or 0.12), 0.08)
        lines.append(
            f"Dialogue: 0,{_ts(start)},{_ts(end)},Pop,,0,0,0,,{ _ass_escape(text) }"
        )
    return "\n".join(lines)


def script_to_ass_fallback(script: str, duration: float, *, width: int = 1080, height: int = 1920) -> str:
    """Chunk script into timed lines if Edge word boundaries missing."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", script) if p.strip()]
    if not parts:
        parts = [script.strip()]
    n = max(len(parts), 1)
    slot = max(duration / n, 0.8)
    fake = []
    t = 0.0
    for p in parts:
        fake.append({"text": p, "start": t, "duration": min(slot, 4.0)})
        t += slot
    # reuse ass but with phrase style - shorten font via same Pop
    # For long phrases, still OK
    return words_to_ass(fake, width=width, height=height)


def _ts(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
