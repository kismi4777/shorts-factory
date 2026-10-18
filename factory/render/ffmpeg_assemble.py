"""FFmpeg-first assembly: stock concat or reddit overlay + audio + ASS subs."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional


def _run(cmd: list[str]) -> None:
    print("  $", " ".join(cmd[:12]), "..." if len(cmd) > 12 else "")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "")[-2000:]
        raise RuntimeError(f"ffmpeg failed ({proc.returncode}): {err}")


def probe_duration(path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(proc.stdout or "{}")
    return float((data.get("format") or {}).get("duration") or 0)


def scale_clip(src: Path, dest: Path, width: int, height: int, duration: Optional[float] = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1"
    )
    cmd = ["ffmpeg", "-y", "-i", str(src), "-vf", vf, "-an"]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", str(dest)]
    _run(cmd)
    return dest


def concat_clips(clips: list[Path], dest: Path, width: int, height: int, total_dur: float) -> Path:
    """Loop/trim clips to cover total_dur, then concat."""
    work = dest.parent / "_scaled"
    work.mkdir(parents=True, exist_ok=True)
    if not clips:
        raise RuntimeError("no clips to concat")

    # one slice per source clip, equal share of total duration (loop sources if few)
    n = max(len(clips), 1)
    target_n = max(n, min(6, int(total_dur / 3) or 1))
    per = max(total_dur / target_n, 2.0)
    scaled: list[Path] = []
    for i in range(target_n):
        src = clips[i % n]
        out = work / f"s_{i:03d}.mp4"
        scale_clip(src, out, width, height, duration=per)
        scaled.append(out)

    list_file = work / "concat.txt"
    list_file.write_text(
        "".join(f"file '{p.resolve().as_posix()}'\n" for p in scaled),
        encoding="utf-8",
    )
    silent = dest.parent / "_video_silent.mp4"
    _run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-t", f"{total_dur:.3f}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(silent),
    ])
    return silent


def loop_background(src: Path, dest: Path, width: int, height: int, duration: float) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1"
    )
    # -stream_loop -1 before -i to loop input
    _run([
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", str(src),
        "-t", f"{duration:.3f}",
        "-vf", vf,
        "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
        str(dest),
    ])
    return dest


def mux_audio_subs(
    video: Path,
    audio: Path,
    ass: Path,
    dest: Path,
    *,
    bgm: Optional[Path] = None,
    bgm_volume: float = 0.12,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Escape ASS path for ffmpeg filter on Windows
    ass_esc = ass.resolve().as_posix().replace(":", "\\:")
    vf = f"ass='{ass_esc}'"

    if bgm and bgm.is_file():
        # voice + quiet bgm
        filter_complex = (
            f"[1:a]volume=1.0[va];"
            f"[2:a]volume={bgm_volume},aloop=loop=-1:size=2e9[bg];"
            f"[va][bg]amix=inputs=2:duration=first:dropout_transition=2[a]"
        )
        _run([
            "ffmpeg", "-y",
            "-i", str(video),
            "-i", str(audio),
            "-i", str(bgm),
            "-filter_complex", filter_complex,
            "-vf", vf,
            "-map", "0:v", "-map", "[a]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            str(dest),
        ])
    else:
        _run([
            "ffmpeg", "-y",
            "-i", str(video),
            "-i", str(audio),
            "-vf", vf,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            str(dest),
        ])
    return dest
