"""
Telegram bot for Shorts Factory.

Flow: topic/script → (Ollama only if short topic) → jobs/*.json
      → git push → GitHub Actions → download mp4 → send to chat.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

ROOT = Path(__file__).resolve().parent
JOBS = ROOT / "jobs"
OUT_GHA = ROOT / "output" / "gha"

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("factory_bot")


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _gh() -> str:
    candidates = [
        os.environ.get("GH_PATH", ""),
        r"C:\Program Files\GitHub CLI\gh.exe",
        r"C:\Program Files (x86)\GitHub CLI\gh.exe",
        "gh",
    ]
    for c in candidates:
        if c and (c == "gh" or Path(c).is_file()):
            return c
    return "gh"


def _run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    timeout: float = 120,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )


def _mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📦 Stock (Pixabay)", callback_data="mode:stock"),
                InlineKeyboardButton("🎮 Reddit/геймплей", callback_data="mode:reddit_gameplay"),
            ]
        ]
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["mode"] = "stock"
    await update.effective_message.reply_text(
        "Shorts Factory.\n\n"
        "1) Режим\n"
        "2) Короткая тема ИЛИ готовый сценарий (Голос:/таймкоды)\n\n"
        "Готовый сценарий → без Ollama.\n"
        "Короткая тема → Ollama → Actions → mp4.",
        reply_markup=_mode_keyboard(),
    )


async def cmd_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text("Режим:", reply_markup=_mode_keyboard())


async def on_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    data = (q.data or "").split(":", 1)
    mode = data[1] if len(data) == 2 else "stock"
    if mode not in ("stock", "reddit_gameplay"):
        mode = "stock"
    context.user_data["mode"] = mode
    label = "Stock" if mode == "stock" else "Reddit/геймплей"
    await q.edit_message_text(
        f"Режим: <b>{label}</b>\nПришли тему или готовый сценарий.",
        parse_mode=ParseMode.HTML,
    )


async def on_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.effective_message.text or "").strip()
    if not text or text.startswith("/"):
        return
    if len(text) < 3:
        await update.effective_message.reply_text("Тема слишком короткая.")
        return
    if len(text) > 8000:
        await update.effective_message.reply_text("Текст слишком длинный (макс ~8000).")
        return

    mode = context.user_data.get("mode") or "stock"
    from factory.script_prep import looks_like_ready_script

    ready = looks_like_ready_script(text)
    status = await update.effective_message.reply_text(
        "Беру готовый сценарий…" if ready else f"Пишу сценарий ({mode})…"
    )
    await update.effective_chat.send_action(ChatAction.TYPING)

    try:
        job_path = await asyncio.to_thread(_make_job, mode, text)
    except Exception as e:
        log.exception("make failed")
        await status.edit_text(f"Сценарий не вышел: {e}")
        return

    await status.edit_text(
        f"Job: <code>{job_path.name}</code>\nПушу в GitHub…",
        parse_mode=ParseMode.HTML,
    )
    pushed_at = datetime.now(timezone.utc)
    try:
        await asyncio.to_thread(_git_push_job, job_path)
    except Exception as e:
        log.exception("git push failed")
        await status.edit_text(f"Не смог запушить job: {e}")
        return

    await status.edit_text("GitHub Actions собирает ролик…")
    try:
        mp4 = await asyncio.to_thread(
            _wait_and_download, job_path, pushed_at=pushed_at, timeout_sec=720
        )
    except Exception as e:
        log.exception("gha failed")
        tip = os.environ.get("LAST_GHA_URL", "")
        await status.edit_text(f"Сборка не вышла: {e}" + (f"\n{tip}" if tip else ""))
        return

    await status.edit_text("Готово, отправляю…")
    try:
        with open(mp4, "rb") as f:
            await update.effective_message.reply_video(
                video=f,
                caption=f"{mode}: {text[:180]}",
                supports_streaming=True,
                reply_markup=_mode_keyboard(),
            )
        await status.delete()
    except Exception as e:
        await status.edit_text(
            f"Файл: <code>{mp4}</code>\nНо в TG не ушло: {e}",
            parse_mode=ParseMode.HTML,
        )


def _make_job(mode: str, topic: str) -> Path:
    from factory.modes.reddit_gameplay import make_reddit_job
    from factory.modes.stock import make_stock_job
    from factory.script_prep import looks_like_ready_script

    # Ollama only needed for short topics
    if not looks_like_ready_script(topic):
        from factory.ollama_script import ensure_ollama

        ensure_ollama()

    if mode == "reddit_gameplay":
        job = make_reddit_job(topic)
    else:
        job = make_stock_job(topic)
    path = JOBS / f"{job.id}.json"
    if not path.is_file():
        raise RuntimeError(f"job file missing: {path}")
    return path


def _git_push_job(job_path: Path) -> None:
    rel = job_path.relative_to(ROOT).as_posix()
    r1 = _run(["git", "add", "--", rel])
    if r1.returncode != 0:
        raise RuntimeError(r1.stderr or r1.stdout or "git add failed")
    st = _run(["git", "status", "--porcelain", "--", rel])
    if not (st.stdout or "").strip():
        _dispatch_workflow(rel)
        return
    msg = f"job: {job_path.stem}"
    r2 = _run(
        [
            "git",
            "-c",
            "user.email=shorts-factory-bot@local",
            "-c",
            "user.name=Shorts Factory Bot",
            "commit",
            "-m",
            msg,
        ]
    )
    if r2.returncode != 0:
        raise RuntimeError(r2.stderr or r2.stdout or "git commit failed")
    r3 = _run(["git", "push", "origin", "HEAD"], timeout=180)
    if r3.returncode != 0:
        raise RuntimeError(r3.stderr or r3.stdout or "git push failed")


def _dispatch_workflow(job_rel: str) -> None:
    gh = _gh()
    repo = os.environ.get("GITHUB_REPO", "kismi4777/shorts-factory")
    r = _run(
        [gh, "workflow", "run", "render-short.yml", "-R", repo, "-f", f"job={job_rel}"],
        timeout=60,
    )
    if r.returncode != 0:
        log.warning("workflow dispatch: %s", r.stderr or r.stdout)


def _parse_gh_time(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _wait_and_download(
    job_path: Path,
    *,
    pushed_at: datetime | None = None,
    timeout_sec: int = 720,
) -> Path:
    gh = _gh()
    repo = os.environ.get("GITHUB_REPO", "kismi4777/shorts-factory")
    stem = job_path.stem
    deadline = time.time() + timeout_sec
    run_id: str | None = None
    floor = (pushed_at or datetime.now(timezone.utc)).timestamp() - 90

    while time.time() < deadline:
        r = _run(
            [
                gh,
                "run",
                "list",
                "-R",
                repo,
                "--workflow",
                "render-short.yml",
                "--limit",
                "20",
                "--json",
                "databaseId,status,conclusion,url,displayTitle,createdAt",
            ],
            timeout=60,
        )
        if r.returncode == 0 and r.stdout.strip():
            runs = json.loads(r.stdout)
            matched = [x for x in runs if stem in (x.get("displayTitle") or "")]
            recent = []
            for x in matched or runs:
                ct = _parse_gh_time(x.get("createdAt") or "")
                if ct and ct.timestamp() < floor:
                    continue
                recent.append(x)
            cand = (matched or recent or runs)[0] if (matched or recent or runs) else None
            if matched:
                cand = matched[0]
            elif recent:
                cand = recent[0]
            if cand:
                run_id = str(cand["databaseId"])
                os.environ["LAST_GHA_URL"] = cand.get("url") or ""
                if cand.get("status") == "completed":
                    if cand.get("conclusion") != "success":
                        raise RuntimeError(
                            f"Actions {cand.get('conclusion')}: {os.environ.get('LAST_GHA_URL')}"
                        )
                    break
        time.sleep(8)
    else:
        raise RuntimeError("timeout waiting for GitHub Actions")

    assert run_id
    dest = OUT_GHA / stem
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)

    dl = _run(
        [gh, "run", "download", run_id, "-R", repo, "-n", "short-output", "-D", str(dest)],
        timeout=360,
    )
    if dl.returncode != 0:
        # file-exists race — try once more on clean dir
        shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True, exist_ok=True)
        dl = _run(
            [gh, "run", "download", run_id, "-R", repo, "-n", "short-output", "-D", str(dest)],
            timeout=360,
        )
        if dl.returncode != 0:
            raise RuntimeError(dl.stderr or dl.stdout or "artifact download failed")

    matches = sorted(dest.rglob("output.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        raise RuntimeError("mp4 not found in artifact")
    return matches[0]


def main() -> None:
    _load_dotenv()
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        import sys

        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN") or "").strip()
    if not token:
        raise SystemExit(
            "Нет TELEGRAM_BOT_TOKEN. Добавь в .env:\n"
            "TELEGRAM_BOT_TOKEN=123:ABC…  (от @BotFather)"
        )
    os.environ.setdefault("PYTHONPATH", str(ROOT))
    if str(ROOT) not in os.sys.path:
        os.sys.path.insert(0, str(ROOT))

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("mode", cmd_mode))
    app.add_handler(CallbackQueryHandler(on_mode, pattern=r"^mode:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_topic))

    log.info("Shorts Factory bot online")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
