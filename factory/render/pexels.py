"""Download vertical-ish stock clips from Pexels (free API key)."""

from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

PEXELS_API = "https://api.pexels.com/videos/search"


def _api_key() -> str:
    return (
        os.environ.get("PEXELS_API_KEY")
        or os.environ.get("pexels_api_key")
        or ""
    ).strip()


def search_video_urls(term: str, *, per_page: int = 8, orientation: str = "portrait") -> list[str]:
    key = _api_key()
    if not key:
        return []
    params = {
        "query": term,
        "per_page": per_page,
        "orientation": orientation,
        "size": "medium",
    }
    headers = {"Authorization": key}
    with httpx.Client(timeout=40.0, headers=headers) as client:
        r = client.get(PEXELS_API, params=params)
        r.raise_for_status()
        data = r.json()
    urls: list[str] = []
    for video in data.get("videos") or []:
        files = video.get("video_files") or []
        # prefer hd portrait-ish
        files_sorted = sorted(
            files,
            key=lambda f: (
                0 if (f.get("width") or 0) <= (f.get("height") or 1) else 1,
                -int(f.get("height") or 0),
            ),
        )
        for f in files_sorted:
            link = f.get("link")
            if link:
                urls.append(link)
                break
    return urls


def download_file(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        with client.stream("GET", url) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
    return dest


def fetch_clips(
    terms: list[str],
    work_dir: Path,
    *,
    count: int = 4,
) -> list[Path]:
    work_dir.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    paths: list[Path] = []
    for term in terms:
        for url in search_video_urls(term):
            name = Path(urlparse(url).path).name or f"clip_{len(paths)}.mp4"
            if name in seen:
                continue
            seen.add(name)
            dest = work_dir / f"{len(paths):02d}_{name}"
            try:
                download_file(url, dest)
                paths.append(dest)
            except Exception as e:
                print(f"  warn pexels download: {e}")
            if len(paths) >= count:
                return paths
    return paths


def ensure_placeholder_clips(work_dir: Path, count: int = 3, seconds: float = 4.0) -> list[Path]:
    """Offline fallback: solid-color motion clips via ffmpeg (no Pexels key)."""
    import subprocess

    work_dir.mkdir(parents=True, exist_ok=True)
    colors = ["0x1a1a2e", "0x16213e", "0x0f3460", "0x533483", "0xe94560"]
    paths: list[Path] = []
    for i in range(count):
        out = work_dir / f"placeholder_{i:02d}.mp4"
        color = colors[i % len(colors)]
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c={color}:s=1080x1920:d={seconds}",
            "-f", "lavfi",
            "-i", f"sine=frequency={220 + i * 40}:duration={seconds}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-shortest", str(out),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        paths.append(out)
    return paths
