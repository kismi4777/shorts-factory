"""CLI: python -m factory make|render|all …"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from factory.job_schema import load_job, save_job
from factory.modes.reddit_gameplay import make_reddit_job
from factory.modes.stock import make_stock_job
from factory.render.pipeline import render_job


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="factory", description="Shorts Factory")
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("make", help="Generate script via Ollama → jobs/*.json")
    m.add_argument("--mode", choices=["stock", "reddit_gameplay"], required=True)
    m.add_argument("--topic", required=True)
    m.add_argument("--language", default="ru")
    m.add_argument("--voice", default="")
    m.add_argument("--background", default="", help="for reddit_gameplay")

    r = sub.add_parser("render", help="Render job JSON locally (FFmpeg + Edge-TTS)")
    r.add_argument("--job", required=True, help="path to jobs/*.json")

    a = sub.add_parser("all", help="make + render in one go")
    a.add_argument("--mode", choices=["stock", "reddit_gameplay"], required=True)
    a.add_argument("--topic", required=True)
    a.add_argument("--language", default="ru")
    a.add_argument("--voice", default="")
    a.add_argument("--background", default="")

    args = p.parse_args(argv)

    if args.cmd == "make":
        job = _make(args)
        print(job.id)
        return 0

    if args.cmd == "render":
        job = load_job(args.job)
        out = render_job(job)
        print(out)
        return 0

    if args.cmd == "all":
        job = _make(args)
        out = render_job(job)
        print(out)
        return 0

    return 1


def _make(args: argparse.Namespace):
    if args.mode == "stock":
        voice = args.voice or "ru-RU-SvetlanaNeural"
        return make_stock_job(args.topic, language=args.language, voice=voice)
    voice = args.voice or "ru-RU-DmitryNeural"
    return make_reddit_job(
        args.topic,
        language=args.language,
        voice=voice,
        background=args.background,
    )


if __name__ == "__main__":
    sys.exit(main())
