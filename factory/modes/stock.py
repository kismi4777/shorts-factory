"""Stock mode — MoneyPrinterTurbo-style: topic → script/terms → Pexels → TTS → render."""

from __future__ import annotations

import re

from factory.job_schema import ShortJob, new_job_id, save_job
from factory.ollama_script import generate_stock_script


def make_stock_job(
    topic: str,
    *,
    language: str = "ru",
    voice: str = "ru-RU-SvetlanaNeural",
    ready_script: str = "",
) -> ShortJob:
    ready = (ready_script or "").strip()
    # длинный текст пользователя = готовый сценарий/факт
    if not ready and len(topic.strip()) >= 280:
        ready = topic.strip()
        topic = _topic_from_long(ready)

    if ready:
        print(f"[stock] ready text, topic={topic!r}, chars={len(ready)}")
        try:
            # длинный факт → короткий spoken script + EN terms
            data = generate_stock_script(
                f"{topic}\n\nФакт для озвучки (сожми в короткий spoken script):\n{ready[:1800]}",
                language=language,
            )
            terms = list(data.get("search_terms") or [])
            title = str(data.get("title") or topic)[:80]
            script = str(data.get("script") or "").strip() or ready[:700]
        except Exception as e:
            print(f"[stock] ollama compress fallback: {e}")
            terms = _fallback_terms(topic, ready)
            title = topic[:80]
            script = ready[:700]
    else:
        print(f"[stock] Ollama script: {topic!r}")
        data = generate_stock_script(topic, language=language)
        script = data["script"]
        terms = list(data.get("search_terms") or [])
        title = str(data.get("title") or topic)[:80]

    terms = _enrich_terms(topic, script, terms)

    job = ShortJob(
        id=new_job_id(topic),
        mode="stock",
        topic=topic,
        language=language,
        script=script,
        search_terms=terms,
        voice=voice,
        meta={"title": title, "engine": "factory+mpt-style"},
    )
    path = save_job(job)
    print(f"[stock] job -> {path}")
    return job


def _topic_from_long(text: str) -> str:
    first = re.split(r"[.!?\n]", text, maxsplit=1)[0].strip()
    words = re.findall(r"[A-Za-zА-Яа-яЁё0-9\-]+", first)
    return " ".join(words[:8]) or text[:60]


def _fallback_terms(topic: str, script: str) -> list[str]:
    blob = f"{topic} {script[:400]}"
    en = re.findall(r"[A-Za-z]{4,}", blob)
    # unique keep order
    seen: set[str] = set()
    out: list[str] = []
    for w in en:
        low = w.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(w)
        if len(out) >= 5:
            break
    return out or ["office", "mystery", "corporate"]


def _enrich_terms(topic: str, script: str, terms: list[str]) -> list[str]:
    """Brand-only queries (Lumon) → 0 hits; add visual EN B-roll keys."""
    out = [t for t in (terms or []) if str(t).strip()]
    low = f"{topic} {script}".lower()
    extras: list[str] = []
    if any(k in low for k in ("зим", "мороз", "winter", "холод")):
        extras += ["snow empty street", "winter city"]
    if any(k in low for k in ("офис", "корпорац", "office", "lumon", "бункер")):
        extras += ["modern office corridor", "underground bunker"]
    if any(k in low for k in ("данн", "data", "компьют")):
        extras += ["server room", "data center"]
    extras += ["mysterious atmosphere", "corporate building night"]
    seen = {t.lower() for t in out}
    for e in extras:
        if e.lower() not in seen:
            out.append(e)
            seen.add(e.lower())
        if len(out) >= 8:
            break
    return out
