import telebot
from telebot import types
import subprocess
import os
import time
import threading
from urllib.parse import urlparse

# 🔐 توكن (تعليمي فقط)
BOT_TOKEN = "8423770288:AAGPjI_9TZQXHUGj9bPn7yvORSwQQDHwGJA"
bot = telebot.TeleBot(BOT_TOKEN)

user_links = {}
chat_locks = {}  # قفل لكل شات

def get_lock(chat_id: int) -> threading.Lock:
    if chat_id not in chat_locks:
        chat_locks[chat_id] = threading.Lock()
    return chat_locks[chat_id]

def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except:
        return ""

def has_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return True
    except:
        return False

def common_ytdlp_args(domain: str):
    args = [
        "--no-playlist",
        "--sleep-requests", "1",
        "--sleep-interval", "1",
        "--max-sleep-interval", "3",
    ]

    # إنستغرام: هيدرز + كوكيز إن وجدت
    if "instagram.com" in domain:
        args += [
            "--user-agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "--add-header", "Referer:https://www.instagram.com/",
            "--add-header", "Origin:https://www.instagram.com",
            "--add-header", "Accept-Language:en-US,en;q=0.9,ar;q=0.8",
        ]
        if os.path.exists("cookies.txt"):
            args += ["--cookies", "cookies.txt"]

    if has_ffmpeg():
        args += ["--merge-output-format", "mp4"]

    return args

def find_file(prefix: str):
    files = [f for f in os.listdir(".") if f.startswith(prefix)]
    if not files:
        return None
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    return files[0]

def ytdlp_download(url, mode, chat_id, msg_id):
    domain = get_domain(url)
    out_prefix = f"dl_{chat_id}_{int(time.time())}"
    out_tmpl = f"{out_prefix}.%(ext)s"
    COMMON = common_ytdlp_args(domain)
    ff = has_ffmpeg()

    # إنستغرام: فيديو فقط + محاولة تجنب الفيديو الأسود (H.264)
    if mode == "ig_video":
        if ff:
            fmt = "bestvideo[vcodec^=avc1]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        else:
            fmt = "best[ext=mp4][vcodec^=avc1]/best[ext=mp4]/best"
    # يوتيوب/تيك توك عالي
    elif mode.endswith("_high"):
        if ff:
            fmt = "bestvideo[vcodec^=avc1]+bestaudio[ext=m4a]/best"
        else:
            fmt = "best[ext=mp4][vcodec^=avc1]/best[ext=mp4]/best"
    # منخفض جدًا
    elif mode.endswith("_low"):
        fmt = "best[height<=360][ext=mp4]/best[height<=360]/best"
    # صوت فقط
    else:
        fmt = "bestaudio/best"

    try:
        bot.edit_message_text("⏳ جاري التحميل...", chat_id, msg_id)
        cmd = ["yt-dlp"] + COMMON + ["-f", fmt, "-o", out_tmpl, url]
        subprocess.run(cmd, check=True)
        return find_file(out_prefix)
    except Exception as e:
        bot.edit_message_text(f"❌ فشل التحميل: {e}", chat_id, msg_id)
        return None

@bot.message_handler(commands=["start"])
def start(m):
    bot.reply_to(
        m,
        "👋 أرسل الرابط\n\n"
        "🔹 يوتيوب/تيك توك: فيديو عالي / فيديو منخفض جدًا / صوت\n"
        "🔹 إنستغرام: فيديو فقط\n"
        "✅ تم تحسين الاستقرار لتجنب خطأ 409 أثناء التحميل."
    )

@bot.message_handler(func=lambda m: m.text and m.text.startswith("http"))
def link(m):
    url = m.text.strip()
    domain = get_domain(url)
    user_links[m.chat.id] = url

    kb = types.InlineKeyboardMarkup(row_width=1)

    if "instagram.com" in domain:
        kb.add(types.InlineKeyboardButton("📸 تحميل فيديو (إنستغرام)", callback_data="ig_video"))
    elif "youtube.com" in domain or "youtu.be" in domain:
        kb.add(
            types.InlineKeyboardButton("🎬 فيديو جودة عالية", callback_data="yt_high"),
            types.InlineKeyboardButton("📉 فيديو جودة منخفضة جدًا", callback_data="yt_low"),
            types.InlineKeyboardButton("🎵 صوت فقط", callback_data="yt_audio"),
        )
    elif "tiktok.com" in domain:
        kb.add(
            types.InlineKeyboardButton("🎬 فيديو جودة عالية", callback_data="tk_high"),
            types.InlineKeyboardButton("📉 فيديو جودة منخفضة جدًا", callback_data="tk_low"),
            types.InlineKeyboardButton("🎵 صوت فقط", callback_data="tk_audio"),
        )
    else:
        kb.add(
            types.InlineKeyboardButton("🎬 فيديو جودة عالية", callback_data="yt_high"),
            types.InlineKeyboardButton("📉 فيديو جودة منخفضة جدًا", callback_data="yt_low"),
            types.InlineKeyboardButton("🎵 صوت فقط", callback_data="yt_audio"),
        )

    bot.reply_to(m, "اختر الخيار 👇", reply_markup=kb)

def handle_download(chat_id, url, mode, status_msg_id):
    lock = get_lock(chat_id)
    if not lock.acquire(blocking=False):
        bot.edit_message_text("⚠️ انتظر، هناك تحميل شغال بالفعل...", chat_id, status_msg_id)
        return

    try:
        path = ytdlp_download(url, mode, chat_id, status_msg_id)

        if path and os.path.exists(path):
            bot.edit_message_text("📤 رفع إلى تيليجرام...", chat_id, status_msg_id)
            with open(path, "rb") as f:
                if mode.endswith("_audio"):
                    bot.send_audio(chat_id, f)
                else:
                    bot.send_video(chat_id, f)

            bot.delete_message(chat_id, status_msg_id)
            try:
                os.remove(path)
            except:
                pass
        else:
            bot.edit_message_text("❌ فشل التحميل", chat_id, status_msg_id)

    finally:
        lock.release()

@bot.callback_query_handler(func=lambda c: c.data in ["ig_video", "yt_high", "yt_low", "yt_audio", "tk_high", "tk_low", "tk_audio"])
def process(c):
    chat_id = c.message.chat.id
    url = user_links.get(chat_id)

    bot.delete_message(chat_id, c.message.message_id)
    msg = bot.send_message(chat_id, "⏳ بدء التحميل...")

    if not url:
        bot.edit_message_text("❌ أرسل الرابط مرة ثانية.", chat_id, msg.message_id)
        return

    # ✅ تشغيل التحميل في Thread (حتى ما يعلق الـ polling ويقل 409)
    t = threading.Thread(target=handle_download, args=(chat_id, url, c.data, msg.message_id), daemon=True)
    t.start()

def run_bot():
    while True:
        try:
            bot.remove_webhook()
            bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            print("Polling crashed:", e)
            time.sleep(5)

print("Bot running 🔥")
run_bot()
