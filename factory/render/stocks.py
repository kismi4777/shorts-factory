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
    # Pixabay API: per_page must be 3..200
    per_page = max(3, min(int(per_page), 200))
    params = {
        "key": key,
        "q": term,
        "per_page": per_page,
        "video_type": "all",
        "safesearch": "true",
    }
    with httpx.Client(timeout=40.0) as client:
        r = client.get(PIXABAY_VIDEOS, params=params)
        r.raise_for_status()
        data = r.json()
    urls: list[str] = []
    # never grab "large" first — often 4K and hangs on slow links
    size_rank = {"medium": 0, "small": 1, "tiny": 2, "large": 9}
    for hit in data.get("hits") or []:
        videos = hit.get("videos") or {}
        candidates = []
        for size_name, info in videos.items():
            info = info or {}
            url = (info.get("url") or "").strip()
            if not url:
                continue
            w = int(info.get("width") or 0)
            h = int(info.get("height") or 0)
            # skip empty / huge 4K packs
            if int(info.get("size") or 0) > 40_000_000:
                continue
            if max(w, h) > 1920 and size_name == "large":
                continue
            portrait = 0 if h >= w else 1
            rank = size_rank.get(size_name, 5)
            candidates.append((rank, portrait, -min(h, 1080), url))
        candidates.sort()
        if candidates:
            urls.append(candidates[0][3])
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


def _curl_bin() -> str:
    import shutil

    # Windows often has curl.exe; Linux/macOS: curl
    for name in ("curl", "curl.exe"):
        path = shutil.which(name)
        if path:
            return path
    return ""


def download_file(url: str, dest: Path) -> Path:
    """Download via curl (cross-platform), fallback httpx."""
    import subprocess

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.unlink(missing_ok=True)

    curl = _curl_bin()
    ok = False
    if curl:
        cmd = [
            curl, "-L", "--fail", "--retry", "2",
            "--connect-timeout", "20", "--max-time", "90",
            "-o", str(tmp), url,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        ok = proc.returncode == 0 and tmp.is_file() and tmp.stat().st_size >= 10_000
        if not ok:
            tmp.unlink(missing_ok=True)

    if not ok:
        timeout = httpx.Timeout(connect=20.0, read=90.0, write=60.0, pool=20.0)
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            with client.stream("GET", url) as r:
                r.raise_for_status()
                written = 0
                with open(tmp, "wb") as f:
                    for chunk in r.iter_bytes(chunk_size=256 * 1024):
                        f.write(chunk)
                        written += len(chunk)
                        if written > 45_000_000:
                            break
        if not tmp.is_file() or tmp.stat().st_size < 10_000:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"download failed: {url[:80]}")
    tmp.replace(dest)
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
                print(f"  ok {label}: {name}")
            except Exception as e:
                print(f"  warn {label} download: {e}")
            if len(paths) >= count:
                return

    # always pad with generic B-roll queries — brand names like "Lumon" often return 0
    padded = list(terms or [])
    for extra in ("office corridor", "winter city empty", "underground bunker", "data center"):
        if extra not in padded:
            padded.append(extra)

    for term in padded:
        if len(paths) >= count:
            break
        # only first 3 urls per term — don't stall on a bad CDN link
        try:
            _ingest(search_pixabay(term)[:3], "pixabay")
        except Exception as e:
            print(f"  warn pixabay search {term!r}: {e}")
        if len(paths) >= count:
            break
        try:
            _ingest(search_pexels(term)[:3], "pexels")
        except Exception as e:
            print(f"  warn pexels search {term!r}: {e}")

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
