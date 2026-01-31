import telebot
from telebot import types
import subprocess
import os
import time
from urllib.parse import urlparse

# 🔐 توكن البوت (لأغراض تعليمية فقط)
BOT_TOKEN = "8423770288:AAGPjI_9TZQXHUGj9bPn7yvORSwQQDHwGJA"
bot = telebot.TeleBot(BOT_TOKEN)

user_links = {}

# =========================
# أدوات مساعدة
# =========================
def get_domain(url):
    try:
        d = urlparse(url).netloc.lower().replace("www.", "")
        return d
    except:
        return ""

def common_ytdlp_args(domain):
    args = [
        "--no-playlist",
        "--sleep-requests", "1",
        "--sleep-interval", "1",
        "--max-sleep-interval", "3",
    ]

    # إعدادات خاصة بإنستغرام
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

    return args

def find_file(prefix):
    files = [f for f in os.listdir(".") if f.startswith(prefix)]
    if not files:
        return None
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    return files[0]

# =========================
# yt-dlp تحميل
# =========================
def ytdlp_download(url, mode, chat_id, msg_id):
    try:
        domain = get_domain(url)
        bot.edit_message_text("⏳ جاري التحميل...", chat_id, msg_id)

        stamp = int(time.time())
        prefix = f"dl_{chat_id}_{stamp}"
        out = f"{prefix}.%(ext)s"

        COMMON = common_ytdlp_args(domain)

        # إنستغرام: فيديو فقط
        if mode == "ig_video":
            fmt = "bestvideo+bestaudio/best"
        # يوتيوب / تيك توك عالي
        elif mode.endswith("_high"):
            fmt = "bestvideo+bestaudio/best"
        # يوتيوب / تيك توك منخفض جدًا
        elif mode.endswith("_low"):
            fmt = "best[height<=360]/best"
        # صوت فقط
        else:
            fmt = "bestaudio/best"

        cmd = ["yt-dlp"] + COMMON + ["-f", fmt, "-o", out, url]
        subprocess.run(cmd, check=True)

        return find_file(prefix)

    except Exception as e:
        bot.edit_message_text(f"❌ خطأ: {e}", chat_id, msg_id)
        return None

# =========================
# أوامر
# =========================
@bot.message_handler(commands=["start"])
def start(m):
    bot.reply_to(
        m,
        "👋 أرسل الرابط\n\n"
        "🔹 يوتيوب / تيك توك:\n"
        "   🎬 فيديو جودة عالية\n"
        "   📉 فيديو جودة منخفضة جدًا\n"
        "   🎵 صوت فقط\n\n"
        "🔹 إنستغرام:\n"
        "   📸 تحميل فيديو فقط\n"
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

@bot.callback_query_handler(func=lambda c: c.data in [
    "ig_video",
    "yt_high", "yt_low", "yt_audio",
    "tk_high", "tk_low", "tk_audio"
])
def process(c):
    chat_id = c.message.chat.id
    url = user_links.get(chat_id)

    bot.delete_message(chat_id, c.message.message_id)
    msg = bot.send_message(chat_id, "⏳ بدء التحميل...")

    if not url:
        bot.edit_message_text("❌ أرسل الرابط مرة ثانية.", chat_id, msg.message_id)
        return

    path = ytdlp_download(url, c.data, chat_id, msg.message_id)

    if path and os.path.exists(path):
        bot.edit_message_text("📤 رفع إلى تيليجرام...", chat_id, msg.message_id)

        with open(path, "rb") as f:
            if c.data.endswith("_audio"):
                bot.send_audio(chat_id, f)
            else:
                bot.send_video(chat_id, f)

        bot.delete_message(chat_id, msg.message_id)
        os.remove(path)
    else:
        bot.edit_message_text("❌ فشل التحميل", chat_id, msg.message_id)

# =========================
# تشغيل
# =========================
print("Bot running (educational token) 🚀")
bot.infinity_polling()
