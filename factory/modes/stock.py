"""Stock mode — MoneyPrinterTurbo-style: topic → script/terms → Pexels → TTS → render."""

from __future__ import annotations

import re

from factory.job_schema import ShortJob, new_job_id, save_job
from factory.ollama_script import generate_stock_script
from factory.script_prep import extract_spoken_script, looks_like_ready_script, topic_slug


def make_stock_job(
    topic: str,
    *,
    language: str = "ru",
    voice: str = "ru-RU-SvetlanaNeural",
    ready_script: str = "",
) -> ShortJob:
    ready = (ready_script or "").strip()
    # длинный / размеченный текст = готовый сценарий
    if not ready and looks_like_ready_script(topic):
        ready = extract_spoken_script(topic) or topic.strip()
        topic = topic_slug(ready)

    if ready:
        print(f"[stock] ready text, topic={topic!r}, chars={len(ready)}")
        try:
            # короткий промпт — иначе Ollama 500
            data = generate_stock_script(
                f"Тема: {topic}\nСожми в spoken script <90 слов + EN search_terms:\n{ready[:500]}",
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
