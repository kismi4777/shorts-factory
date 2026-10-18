"""Stock mode — MoneyPrinterTurbo-style: topic → script/terms → Pexels → TTS → render."""

from __future__ import annotations

from factory.job_schema import ShortJob, new_job_id, save_job
from factory.ollama_script import generate_stock_script


def make_stock_job(topic: str, *, language: str = "ru", voice: str = "ru-RU-SvetlanaNeural") -> ShortJob:
    print(f"🧠 Ollama stock script: {topic!r}")
    data = generate_stock_script(topic, language=language)
    job = ShortJob(
        id=new_job_id(topic),
        mode="stock",
        topic=topic,
        language=language,
        script=data["script"],
        search_terms=list(data.get("search_terms") or []),
        voice=voice,
        meta={"title": data.get("title") or topic, "engine": "factory+mpt-style"},
    )
    path = save_job(job)
    print(f"💾 job → {path}")
    return job
