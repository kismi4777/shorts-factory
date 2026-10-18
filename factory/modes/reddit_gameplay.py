"""Reddit/gameplay mode — ShortGPT-style story over looped background clip."""

from __future__ import annotations

from factory.job_schema import ROOT, ShortJob, new_job_id, save_job
from factory.ollama_script import generate_reddit_script


def make_reddit_job(
    topic: str,
    *,
    language: str = "ru",
    voice: str = "ru-RU-DmitryNeural",
    background: str = "",
) -> ShortJob:
    print(f"🧠 Ollama reddit/gameplay script: {topic!r}")
    data = generate_reddit_script(topic, language=language)
    bg = background
    if not bg:
        defaults = sorted((ROOT / "assets" / "backgrounds").glob("*.mp4"))
        if defaults:
            bg = str(defaults[0].relative_to(ROOT)).replace("\\", "/")
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
    print(f"💾 job → {path}")
    return job
