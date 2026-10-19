"""Reddit/gameplay mode — ShortGPT-style story over looped background clip."""

from __future__ import annotations

import random

from factory.job_schema import ROOT, ShortJob, new_job_id, save_job
from factory.ollama_script import generate_reddit_script
from factory.script_prep import extract_spoken_script, looks_like_ready_script, topic_slug


def make_reddit_job(
    topic: str,
    *,
    language: str = "ru",
    voice: str = "ru-RU-DmitryNeural",
    background: str = "",
) -> ShortJob:
    raw = (topic or "").strip()
    if looks_like_ready_script(raw):
        script = extract_spoken_script(raw)
        if not script:
            raise RuntimeError("не смог вытащить текст озвучки из сценария")
        title = topic_slug(script)
        hook = script.split(".")[0][:160]
        print(f"[reddit] ready script, chars={len(script)} (skip Ollama)")
        data = {"script": script, "title": title, "hook": hook}
        topic_for_id = title
    else:
        print(f"[reddit] Ollama script: {raw[:80]!r}")
        data = generate_reddit_script(raw, language=language)
        topic_for_id = raw

    bg = background
    if not bg:
        # Prefer Release set (01–10); fall back to any local bed
        beds = list((ROOT / "assets" / "backgrounds").glob("gameplay_*.mp4"))
        release_like = [p for p in beds if p.stem.split("_")[-1].isdigit() and int(p.stem.split("_")[-1]) <= 10]
        pool = release_like or beds
        if pool:
            pick = random.choice(pool)
            bg = str(pick.relative_to(ROOT)).replace("\\", "/")
            print(f"[reddit] background -> {bg}")
        else:
            # Actions fetches beds from Release; empty → first available there
            bg = ""
            print("[reddit] no local beds — GHA will pick from Release")

    job = ShortJob(
        id=new_job_id(topic_for_id),
        mode="reddit_gameplay",
        topic=topic_for_id[:120],
        language=language,
        script=data["script"],
        search_terms=[],
        voice=voice,
        background=bg,
        meta={
            "title": data.get("title") or topic_for_id,
            "hook": data.get("hook") or "",
            "engine": "factory+shortgpt-style",
            "ready_script": looks_like_ready_script(raw),
        },
    )
    path = save_job(job)
    print(f"[reddit] job -> {path}")
    return job
