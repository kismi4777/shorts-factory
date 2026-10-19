"""End-to-end render for a ShortJob (stock | reddit_gameplay)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from factory.job_schema import OUT_DIR, ShortJob, ROOT
from factory.render import ffmpeg_assemble as ff
from factory.render import stocks
from factory.render import tts


def render_job(job: ShortJob, *, work_root: Path | None = None) -> Path:
    work = work_root or (OUT_DIR / job.id / "work")
    work.mkdir(parents=True, exist_ok=True)
    final_dir = OUT_DIR / job.id
    final_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = final_dir / "output.mp4"

    from factory.script_prep import extract_spoken_script, looks_like_ready_script

    script = (job.script or "").strip()
    if looks_like_ready_script(script):
        script = extract_spoken_script(script) or script
    if not script:
        raise RuntimeError("job.script is empty — generate with Ollama first")

    print(f"[render] TTS ({job.voice})")
    mp3 = work / "voice.mp3"
    words = tts.synthesize(script, job.voice, mp3)
    audio_dur = ff.probe_duration(mp3)
    if audio_dur <= 0:
        audio_dur = max((w.get("start", 0) + w.get("duration", 0) for w in words), default=10)

    ass_path = work / "subs.ass"
    if words:
        ass_path.write_text(
            tts.words_to_ass(words, width=job.width, height=job.height),
            encoding="utf-8",
        )
    else:
        ass_path.write_text(
            tts.script_to_ass_fallback(script, audio_dur, width=job.width, height=job.height),
            encoding="utf-8",
        )

    print(f"[render] video bed ({job.mode})")
    if job.mode == "reddit_gameplay":
        bg = _resolve_background(job.background)
        video_silent = ff.loop_background(bg, work / "bed.mp4", job.width, job.height, audio_dur + 0.3)
    else:
        clips_dir = work / "clips"
        clips = stocks.fetch_clips(job.search_terms or [job.topic], clips_dir, count=4)
        if not clips:
            key_on = bool(stocks._pixabay_key() or stocks._pexels_key())
            if key_on:
                raise RuntimeError(
                    "Pixabay key is set but no clips downloaded — check search terms / CDN"
                )
            print("  [warn] no stock API key -> placeholders")
            clips = stocks.ensure_placeholder_clips(clips_dir, count=3, seconds=4.0)
        video_silent = ff.concat_clips(clips, work / "bed.mp4", job.width, job.height, audio_dur + 0.3)

    bgm = Path(job.bgm) if job.bgm else None
    if bgm and not bgm.is_file():
        cand = ROOT / job.bgm
        bgm = cand if cand.is_file() else None

    print("[render] mux + burn subs")
    # run mux from work dir so ass path is simple
    cwd = Path.cwd()
    try:
        os.chdir(work)
        # copy inputs next to cwd-relative names
        v_local = Path("bed_in.mp4")
        a_local = Path("voice.mp3")
        s_local = Path("subs.ass")
        if not v_local.exists():
            shutil.copy2(video_silent, v_local)
        if Path(mp3).resolve() != (work / "voice.mp3").resolve():
            shutil.copy2(mp3, a_local)
        out_local = Path("final.mp4")
        _mux_relative(v_local, a_local, s_local, out_local, bgm=bgm)
        shutil.copy2(out_local, out_mp4)
    finally:
        os.chdir(cwd)

    print(f"[render] done {out_mp4}")
    return out_mp4


def _resolve_background(rel: str) -> Path:
    default_dir = ROOT / "assets" / "backgrounds"

    def _any_bed() -> Path | None:
        beds = sorted(default_dir.glob("gameplay_*.mp4")) or sorted(default_dir.glob("*.mp4"))
        return beds[0] if beds else None

    if not rel:
        hit = _any_bed()
        if not hit:
            raise RuntimeError(
                "no background video — put an mp4 in assets/backgrounds/ "
                "or set job.background (Actions: backgrounds Release)"
            )
        return hit
    p = Path(rel)
    if p.is_file():
        return p
    for cand in (ROOT / rel, default_dir / Path(rel).name, default_dir / rel):
        if cand.is_file():
            return cand
    # local job may point at gameplay_38 while GHA only has 01–10
    hit = _any_bed()
    if hit:
        print(f"  [warn] background missing {rel!r} -> fallback {hit.name}")
        return hit
    raise RuntimeError(f"background not found: {rel}")


def _mux_relative(
    video: Path,
    audio: Path,
    ass: Path,
    dest: Path,
    *,
    bgm: Path | None,
) -> None:
    """Burn ASS using relative paths (reliable on Windows + GHA)."""
    import subprocess

    vf = f"ass={ass.name}"
    if bgm and bgm.is_file():
        bgm_copy = Path("bgm" + bgm.suffix)
        if not bgm_copy.exists():
            shutil.copy2(bgm, bgm_copy)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video),
            "-i", str(audio),
            "-i", str(bgm_copy),
            "-filter_complex",
            "[1:a]volume=1.0[va];[2:a]volume=0.12,aloop=loop=-1:size=2e9[bg];"
            "[va][bg]amix=inputs=2:duration=first:dropout_transition=2[a]",
            "-vf", vf,
            "-map", "0:v", "-map", "[a]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            str(dest),
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video),
            "-i", str(audio),
            "-vf", vf,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            str(dest),
        ]
    print("  $", " ".join(cmd[:14]), "...")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # fallback: no burn-in, just mux
        print("  [warn] ass burn failed, mux without subs")
        print((proc.stderr or "")[-800:])
        cmd2 = [
            "ffmpeg", "-y",
            "-i", str(video),
            "-i", str(audio),
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            str(dest),
        ]
        proc2 = subprocess.run(cmd2, capture_output=True, text=True)
        if proc2.returncode != 0:
            raise RuntimeError((proc2.stderr or "")[-1500:])
