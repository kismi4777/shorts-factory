"""Reddit/gameplay mode — ShortGPT-style story over looped background clip."""

from __future__ import annotations

import random

from factory.job_schema import ROOT, ShortJob, new_job_id, save_job
from factory.ollama_script import generate_reddit_script


def make_reddit_job(
    topic: str,
    *,
    language: str = "ru",
    voice: str = "ru-RU-DmitryNeural",
    background: str = "",
) -> ShortJob:
    print(f"[reddit] Ollama script: {topic!r}")
    data = generate_reddit_script(topic, language=language)
    bg = background
    if not bg:
        defaults = list((ROOT / "assets" / "backgrounds").glob("*.mp4"))
        if defaults:
            pick = random.choice(defaults)
            bg = str(pick.relative_to(ROOT)).replace("\\", "/")
            print(f"[reddit] background -> {bg}")
    job = ShortJob(
        id=new_job_id(topic),
        mode="reddit_gameplay",
        topic=topic,
        language=language,
        script=data["script"],
        search_terms=[],
        voice=voice,
        background=bg,
        meta={
            "title": data.get("title") or topic,
            "hook": data.get("hook") or "",
            "engine": "factory+shortgpt-style",
        },
    )
    path = save_job(job)
    print(f"[reddit] job -> {path}")
    return job
