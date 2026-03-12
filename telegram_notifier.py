"""
telegram_notifier.py
────────────────────
Sends messages (and optionally files) to your Telegram bot.

SETUP: Set these two environment variables (or GitHub Secrets):
  TELEGRAM_BOT_TOKEN  — from BotFather
  TELEGRAM_CHAT_ID    — your personal chat ID

HOW TO GET YOUR CHAT ID:
  1. Start your bot on Telegram (send it /start)
  2. Visit: https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
  3. Look for "chat":{"id": 123456789} — that number is your CHAT_ID
"""

import os
import requests

BOT_TOKEN     = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID       = os.environ.get("TELEGRAM_CHAT_ID",   "")
TELEGRAM_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"


def _check_creds() -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️  Telegram: BOT_TOKEN or CHAT_ID not set — skipping notification.")
        return False
    return True


def _post(endpoint: str, **kwargs) -> dict | None:
    """Fire-and-forget POST — never raises so it never breaks the main pipeline."""
    try:
        r    = requests.post(f"{TELEGRAM_BASE}/{endpoint}", timeout=15, **kwargs)
        body = r.json()
        if not body.get("ok"):
            print(f"⚠️  Telegram API error: {body.get('description', body)}")
        return body
    except Exception as e:
        print(f"⚠️  Telegram send failed: {e}")
        return None


# ── PUBLIC API ────────────────────────────────────────────────────────────────

def send(text: str, parse_mode: str = "HTML") -> None:
    if not _check_creds(): return
    _post("sendMessage", json={
        "chat_id": CHAT_ID, "text": text, "parse_mode": parse_mode,
    })


def send_video(video_path: str, caption: str = "") -> None:
    if not _check_creds(): return
    if not os.path.exists(video_path):
        send(f"⚠️ Video not found: <code>{video_path}</code>")
        return
    mb = os.path.getsize(video_path) / 1024 / 1024
    if mb > 50:
        send(f"⚠️ Video is <b>{mb:.1f} MB</b> — too large for Telegram (50 MB limit).")
        return
    with open(video_path, "rb") as f:
        _post("sendVideo", data={
            "chat_id": CHAT_ID, "caption": caption[:1024], "parse_mode": "HTML",
        }, files={"video": f})


# ── CONVENIENCE WRAPPERS ──────────────────────────────────────────────────────

def notify_start() -> None:
    send("🎬 <b>Daily Word Reel — Starting</b>\nFetching today's word…")

def notify_word(word: str, pos: str, defn: str) -> None:
    send(
        f"📖 <b>Today's word:</b> <code>{word.upper()}</code>\n"
        f"🏷 <i>{pos.capitalize()}</i>\n"
        f"📝 {defn}"
    )

def notify_render_done(output_path: str) -> None:
    mb = os.path.getsize(output_path) / 1024 / 1024 if os.path.exists(output_path) else 0
    send(
        f"✅ <b>Reel rendered!</b>\n"
        f"📁 <code>{os.path.basename(output_path)}</code>  ({mb:.1f} MB)\n"
        f"⏱ 74s  |  1080×1920  |  9:16"
    )

def notify_upload_start() -> None:
    send("📤 <b>Uploading reel to Instagram…</b>")

def notify_upload_phase(phase: str, detail: str = "") -> None:
    icons = {"session": "🔗", "uploading": "⬆️", "processing": "⏳", "publishing": "🚀"}
    icon  = icons.get(phase, "•")
    msg   = f"{icon} <b>{phase.capitalize()}</b>"
    if detail:
        msg += f"\n<code>{detail[:200]}</code>"
    send(msg)

def notify_live(post_id: str, word: str) -> None:
    send(
        f"🎉 <b>Reel is LIVE on Instagram!</b>\n"
        f"🆔 Post ID: <code>{post_id}</code>\n"
        f"💬 Word: <b>{word.upper()}</b>"
    )

def notify_error(stage: str, error: str) -> None:
    send(f"❌ <b>Error at: {stage}</b>\n<pre>{str(error)[:800]}</pre>")

def notify_skipped(reason: str) -> None:
    send(f"⏭ <b>Upload skipped</b>\n{reason}")