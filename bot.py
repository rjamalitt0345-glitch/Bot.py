#!/usr/bin/env python3
"""
Universal Video Downloader - Telegram Bot
- Upload timeout fix kiya
- File size limit kam ki taaki upload jaldi ho
- Read timeout badha diya
"""

import os
import re
import json
import glob
import subprocess
import logging
from telegram import Update
from telegram.request import HTTPXRequest
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ─── CONFIG ──────────────────────────────────────────────────────────────────
BOT_TOKEN    = "8648341248:AAEmDjz8NwDLpBnhzrjveRDY87i_1tSOicw"
DOWNLOAD_DIR = "downloads"
MAX_SIZE     = 45 * 1024 * 1024   # 45MB (thoda kam rakha taaki upload ho sake)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

def extract_url(text: str) -> str | None:
    urls = re.findall(r'https?://[^\s\'"<>]+', text)
    return urls[0].rstrip(".,)\"'") if urls else None

def human_size(n: int) -> str:
    if not n:
        return "Unknown"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"

def cleanup_downloads():
    if os.path.exists(DOWNLOAD_DIR):
        for f in os.listdir(DOWNLOAD_DIR):
            try:
                os.remove(os.path.join(DOWNLOAD_DIR, f))
            except Exception:
                pass

def get_latest_file() -> str | None:
    files = glob.glob(os.path.join(DOWNLOAD_DIR, "*"))
    files = [f for f in files if not f.endswith(".part") and os.path.isfile(f)]
    return max(files, key=os.path.getmtime) if files else None

# ─── VIDEO INFO ──────────────────────────────────────────────────────────────

def get_video_info(url: str) -> dict | None:
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-playlist", "--no-warnings", url],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            info = json.loads(result.stdout)
            return {
                "title":    info.get("title", "video"),
                "duration": info.get("duration", 0),
                "uploader": info.get("uploader", ""),
            }
    except Exception as e:
        logger.error(f"get_info: {e}")
    return None

# ─── DOWNLOAD ────────────────────────────────────────────────────────────────

def download_video(url: str) -> str | None:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    cleanup_downloads()
    output = os.path.join(DOWNLOAD_DIR, "%(title).50s.%(ext)s")

    # Formats: pehle 480p try karo (jaldi upload hoga), phir 720p
    formats = [
        # 480p MP4 — Termux ke liye best (jaldi upload)
        "bestvideo[ext=mp4][height<=480]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best[height<=480]",
        # 720p fallback
        "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[height<=720]",
        # Kuch bhi
        "best",
    ]

    for fmt in formats:
        try:
            cmd = [
                "yt-dlp",
                "-o", output,
                "--no-playlist",
                "--no-warnings",
                "-f", fmt,
                "--merge-output-format", "mp4",
                "--max-filesize", "44M",
                "--no-part",
                url,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                filepath = get_latest_file()
                if filepath and os.path.getsize(filepath) > 0:
                    size = os.path.getsize(filepath)
                    logger.info(f"Downloaded: {filepath} ({human_size(size)})")
                    return filepath
        except Exception as e:
            logger.error(f"download: {e}")

    return None


def download_audio(url: str) -> str | None:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    cleanup_downloads()
    output = os.path.join(DOWNLOAD_DIR, "%(title).50s.%(ext)s")
    try:
        result = subprocess.run(
            ["yt-dlp", "-o", output, "--no-playlist", "--no-warnings",
             "-x", "--audio-format", "mp3", "--audio-quality", "128K", "--no-part", url],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode == 0:
            return get_latest_file()
    except Exception as e:
        logger.error(f"audio: {e}")
    return None

# ─── SEND FILE ───────────────────────────────────────────────────────────────

async def send_file(filepath: str, info: dict | None, update: Update, msg) -> None:
    actual_size = os.path.getsize(filepath)

    if actual_size > MAX_SIZE:
        os.remove(filepath)
        await msg.edit_text(
            f"⚠️ File *{human_size(actual_size)}* — limit se zyada.\n"
            "Chhoti quality try ho rahi hai...",
            parse_mode="Markdown",
        )
        return

    await msg.edit_text(f"📤 Upload ho raha hai ({human_size(actual_size)})...")

    ext     = filepath.rsplit(".", 1)[-1].lower()
    title   = info["title"][:40] if info else os.path.basename(filepath)
    caption = f"✅ *{title}*\n📦 {human_size(actual_size)}"

    try:
        with open(filepath, "rb") as f:
            if ext in ("mp4", "mkv", "avi", "mov", "webm", "m4v"):
                await update.message.reply_video(
                    video=f,
                    caption=caption,
                    parse_mode="Markdown",
                    supports_streaming=True,
                    read_timeout=300,      # ✅ 5 min upload timeout
                    write_timeout=300,
                    connect_timeout=60,
                )
            elif ext in ("mp3", "m4a", "aac", "ogg", "flac"):
                await update.message.reply_audio(
                    audio=f,
                    caption=caption,
                    parse_mode="Markdown",
                    read_timeout=300,
                    write_timeout=300,
                    connect_timeout=60,
                )
            else:
                await update.message.reply_document(
                    document=f,
                    caption=caption,
                    parse_mode="Markdown",
                    read_timeout=300,
                    write_timeout=300,
                    connect_timeout=60,
                )
        await msg.delete()

    except Exception as e:
        logger.error(f"send_file: {e}")
        await msg.edit_text(f"❌ Upload error: {e}")
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)

# ─── BOT HANDLERS ────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 *Universal Video Downloader Bot*\n\n"
        "Koi bhi video link bhejo!\n\n"
        "✅ *Supported:*\n"
        "• YouTube\n"
        "• Instagram Reels\n"
        "• Facebook Videos\n"
        "• Twitter/X\n"
        "• TikTok\n"
        "• Reddit, Vimeo aur 1000+ sites\n\n"
        "🎵 Sirf audio:\n`/audio <link>`",
        parse_mode="Markdown",
    )


async def audio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: `/audio <url>`",
            parse_mode="Markdown",
        )
        return

    url = context.args[0]
    msg = await update.message.reply_text("🎵 Audio download ho raha hai...")
    info = get_video_info(url)
    filepath = download_audio(url)

    if not filepath:
        await msg.edit_text("❌ Audio download fail hua.")
        return

    await send_file(filepath, info, update, msg)


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    url  = extract_url(text)

    if not url:
        await update.message.reply_text("❌ Koi URL nahi mili.")
        return

    msg = await update.message.reply_text("⏳ Info fetch ho rahi hai...")

    info = get_video_info(url)
    if info:
        dur = f"{int(info['duration']//60)}:{int(info['duration']%60):02d}" if info['duration'] else "?"
        await msg.edit_text(
            f"📹 *{info['title'][:50]}*\n"
            f"⏱ {dur} | 👤 {info['uploader']}\n\n"
            f"⬇️ Download ho raha hai...",
            parse_mode="Markdown",
        )
    else:
        await msg.edit_text("⬇️ Download ho raha hai...")

    filepath = download_video(url)

    if not filepath:
        await msg.edit_text(
            "❌ Download fail hua.\n\n"
            "• Link private ho sakta hai\n"
            "• Age restricted video\n"
            "• Unsupported site\n\n"
            "Koi aur link try karo."
        )
        return

    await send_file(filepath, info, update, msg)

# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    # ✅ HTTPXRequest se timeout badha diya
    request = HTTPXRequest(
        read_timeout=300,
        write_timeout=300,
        connect_timeout=60,
        pool_timeout=60,
    )

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .request(request)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("audio", audio_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))

    print("🤖 Bot chal raha hai...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
