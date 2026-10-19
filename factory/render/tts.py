"""Edge-TTS voiceover + CapCut-style word-synced ASS captions."""

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
    word_events: list[dict[str, Any]] = []
    sentence_events: list[dict[str, Any]] = []
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    with open(mp3_path, "wb") as f:
        async for chunk in communicate.stream():
            kind = chunk.get("type")
            if kind == "audio":
                f.write(chunk["data"])
            elif kind == "WordBoundary":
                word_events.append(_boundary(chunk))
            elif kind == "SentenceBoundary":
                sentence_events.append(_boundary(chunk))
    if word_events:
        return word_events
    # RU Edge voices often only emit SentenceBoundary — split into words by weight
    return _expand_sentences_to_words(sentence_events)


def _boundary(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "text": (chunk.get("text") or "").strip(),
        "start": float(chunk.get("offset", 0)) / 10_000_000,
        "duration": float(chunk.get("duration", 0)) / 10_000_000,
    }


def _expand_sentences_to_words(sentences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    for sent in sentences:
        text = (sent.get("text") or "").strip()
        if not text:
            continue
        tokens = re.findall(r"\S+", text)
        if not tokens:
            continue
        weights = [max(len(re.sub(r"\W+", "", tok, flags=re.UNICODE)), 1) for tok in tokens]
        total = float(sum(weights)) or 1.0
        t0 = float(sent.get("start") or 0)
        dur = max(float(sent.get("duration") or 0.5), 0.2)
        # small lead-in hush inside the sentence window
        cursor = t0
        for tok, w in zip(tokens, weights):
            piece = dur * (w / total)
            words.append({"text": tok, "start": cursor, "duration": max(piece, 0.06)})
            cursor += piece
    return words


def synthesize(text: str, voice: str, mp3_path: Path) -> list[dict[str, Any]]:
    clean = re.sub(r"\s+", " ", (text or "").strip())
    # strip leftover quote titles that confuse TTS
    clean = re.sub(r"^[«\"].*?[»\"]\s*", "", clean).strip() or clean
    if not clean:
        raise RuntimeError("empty TTS text")
    return asyncio.run(_synth(clean, voice, mp3_path))


def words_to_ass(words: list[dict[str, Any]], *, width: int = 1080, height: int = 1920) -> str:
    """CapCut-style: 2–4 words on screen, active word pops + yellow highlight."""
    cleaned = []
    for w in words:
        text = (w.get("text") or "").strip()
        if not text:
            continue
        cleaned.append(
            {
                "text": text,
                "start": float(w.get("start") or 0),
                "duration": max(float(w.get("duration") or 0.12), 0.06),
            }
        )
    if not cleaned:
        return script_to_ass_fallback("", 1.0, width=width, height=height)

    groups = _group_words(cleaned, max_words=3, max_chars=24)
    # DejaVu = available on Ubuntu GHA; Arial Black often missing there
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: CapCut,DejaVu Sans,78,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,0,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for group in groups:
        for i, w in enumerate(group):
            start = w["start"]
            if i + 1 < len(group):
                end = group[i + 1]["start"]
            else:
                end = start + max(w["duration"], 0.14)
            end = max(end, start + 0.08)
            body = _capcut_line(group, active_idx=i)
            lines.append(
                f"Dialogue: 0,{_ts(start)},{_ts(end)},CapCut,,0,0,0,,{body}"
            )
    return "\n".join(lines)


def _group_words(
    words: list[dict[str, Any]],
    *,
    max_words: int = 3,
    max_chars: int = 24,
) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    cur: list[dict[str, Any]] = []
    for w in words:
        text = w["text"]
        chars = sum(len(x["text"]) for x in cur) + len(cur) + len(text)
        flush_before = bool(cur) and (len(cur) >= max_words or chars > max_chars)
        if flush_before:
            groups.append(cur)
            cur = []
        cur.append(w)
        if re.search(r"[.!?…]$", text):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def _capcut_line(group: list[dict[str, Any]], *, active_idx: int) -> str:
    """Build one ASS line: inactive white, active yellow with pop-in scale."""
    parts: list[str] = []
    for i, w in enumerate(group):
        word = _ass_escape(w["text"])
        if i == active_idx:
            # pop: start big → settle; yellow (&H0000FFFF = BGR)
            parts.append(
                r"{\c&H0000FFFF&\fscx128\fscy128\t(0,90,\fscx100\fscy100)}"
                + word
                + r"{\c&H00FFFFFF&\fscx100\fscy100}"
            )
        else:
            parts.append(r"{\c&H00FFFFFF&\fscx100\fscy100}" + word)
    return " ".join(parts)


def script_to_ass_fallback(script: str, duration: float, *, width: int = 1080, height: int = 1920) -> str:
    """Chunk script into timed lines if Edge boundaries missing."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", script) if p.strip()]
    if not parts:
        parts = [(script or "").strip() or "…"]
    n = max(len(parts), 1)
    slot = max(duration / n, 0.8)
    fake_sentences = []
    t = 0.0
    for p in parts:
        fake_sentences.append({"text": p, "start": t, "duration": min(slot, 5.0)})
        t += slot
    return words_to_ass(_expand_sentences_to_words(fake_sentences), width=width, height=height)


def _ts(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
