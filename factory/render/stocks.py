"""Stock video download: Pixabay (default) + optional Pexels fallback."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import httpx

PIXABAY_VIDEOS = "https://pixabay.com/api/videos/"
PEXELS_API = "https://api.pexels.com/videos/search"


def _load_dotenv() -> None:
    """Minimal .env loader (no extra dependency)."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.is_file():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except OSError:
        pass


def _pixabay_key() -> str:
    _load_dotenv()
    return (
        os.environ.get("PIXABAY_API_KEY")
        or os.environ.get("pixabay_api_key")
        or ""
    ).strip()


def _pexels_key() -> str:
    _load_dotenv()
    return (
        os.environ.get("PEXELS_API_KEY")
        or os.environ.get("pexels_api_key")
        or ""
    ).strip()


def search_pixabay(term: str, *, per_page: int = 10) -> list[str]:
    key = _pixabay_key()
    if not key:
        return []
    params = {
        "key": key,
        "q": term,
        "per_page": per_page,
        "video_type": "film",
        "safesearch": "true",
    }
    with httpx.Client(timeout=40.0) as client:
        r = client.get(PIXABAY_VIDEOS, params=params)
        r.raise_for_status()
        data = r.json()
    urls: list[str] = []
    for hit in data.get("hits") or []:
        videos = hit.get("videos") or {}
        # prefer medium, then large, then small; pick portrait if available
        candidates = []
        for size_name in ("medium", "large", "small", "tiny"):
            info = videos.get(size_name) or {}
            url = (info.get("url") or "").strip()
            if not url:
                continue
            w = int(info.get("width") or 0)
            h = int(info.get("height") or 0)
            portrait = 0 if h >= w else 1
            candidates.append((portrait, -h, url))
        candidates.sort()
        if candidates:
            urls.append(candidates[0][2])
    return urls


def search_pexels(term: str, *, per_page: int = 8) -> list[str]:
    key = _pexels_key()
    if not key:
        return []
    params = {
        "query": term,
        "per_page": per_page,
        "orientation": "portrait",
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
    """Try Pixabay first, then Pexels."""
    work_dir.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    paths: list[Path] = []

    def _ingest(urls: list[str], label: str) -> None:
        nonlocal paths
        for url in urls:
            name = Path(urlparse(url).path).name or f"clip_{len(paths)}.mp4"
            if "?" in name:
                name = name.split("?", 1)[0]
            if name in seen:
                continue
            seen.add(name)
            dest = work_dir / f"{len(paths):02d}_{name}"
            try:
                download_file(url, dest)
                paths.append(dest)
                print(f"  ↓ {label}: {name}")
            except Exception as e:
                print(f"  warn {label} download: {e}")
            if len(paths) >= count:
                return

    for term in terms:
        if len(paths) >= count:
            break
        _ingest(search_pixabay(term), "pixabay")
        if len(paths) >= count:
            break
        _ingest(search_pexels(term), "pexels")

    return paths


def ensure_placeholder_clips(work_dir: Path, count: int = 3, seconds: float = 4.0) -> list[Path]:
    """Offline fallback when no stock API keys."""
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
