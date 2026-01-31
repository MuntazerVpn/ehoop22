import telebot
from telebot import types
import subprocess
import os

# 🔐 توكن البوت (لأغراض تعليمية فقط)
BOT_TOKEN = "8423770288:AAGPjI_9TZQXHUGj9bPn7yvORSwQQDHwGJA"

bot = telebot.TeleBot(BOT_TOKEN)

user_links = {}

# =========================
# 🔥 yt-dlp تحميل
# =========================
def ytdlp_download(url, mode, chat_id, msg_id):
    try:
        bot.edit_message_text("⏳ جاري التحميل...", chat_id, msg_id)

        out_template = f"download_{chat_id}.%(ext)s"

        if mode == "audio":
            # 🎵 صوت فقط بدون تحويل
            cmd = [
                "yt-dlp",
                "-f", "bestaudio/best",
                "--no-playlist",
                "-o", out_template,
                url
            ]

        elif mode == "video_high":
            # 🎬 فيديو جودة عالية
            cmd = [
                "yt-dlp",
                "-f", "mp4/bestvideo+bestaudio/best",
                "--no-playlist",
                "-o", out_template,
                url
            ]

        else:  # video_low
            # 📉 فيديو جودة منخفضة جدًا
            cmd = [
                "yt-dlp",
                "-f", "mp4[height<=360]/best",
                "--no-playlist",
                "-o", out_template,
                url
            ]

        subprocess.run(cmd, check=True)

        for f in os.listdir("."):
            if f.startswith(f"download_{chat_id}."):
                return f

        return None

    except Exception as e:
        bot.edit_message_text(f"❌ خطأ: {e}", chat_id, msg_id)
        return None

# =========================
# 🤖 أوامر
# =========================
@bot.message_handler(commands=["start"])
def start(m):
    bot.reply_to(
        m,
        "👋 أرسل الرابط\n\n"
        "🎬 فيديو جودة عالية\n"
        "📉 فيديو جودة منخفضة جدًا\n"
        "🎵 صوت فقط (بدون مقطع)\n\n"
        "⚡ بوت تعليمي باستخدام yt-dlp"
    )

@bot.message_handler(func=lambda m: m.text and m.text.startswith("http"))
def link(m):
    user_links[m.chat.id] = m.text

    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🎬 فيديو جودة عالية", callback_data="video_high"),
        types.InlineKeyboardButton("📉 فيديو جودة منخفضة جدًا", callback_data="video_low"),
        types.InlineKeyboardButton("🎵 صوت فقط", callback_data="audio")
    )

    bot.reply_to(m, "اختر الصيغة 👇", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data in ["video_high", "video_low", "audio"])
def process(c):
    chat_id = c.message.chat.id
    url = user_links.get(chat_id)

    bot.delete_message(chat_id, c.message.message_id)
    msg = bot.send_message(chat_id, "⏳ بدء التحميل...")

    path = ytdlp_download(url, c.data, chat_id, msg.message_id)

    if path and os.path.exists(path):
        bot.edit_message_text("📤 رفع إلى تيليجرام...", chat_id, msg.message_id)

        with open(path, "rb") as f:
            if c.data == "audio":
                bot.send_audio(chat_id, f)
            else:
                bot.send_video(chat_id, f)

        bot.delete_message(chat_id, msg.message_id)
        os.remove(path)
    else:
        bot.edit_message_text("❌ فشل التحميل", chat_id, msg.message_id)

# =========================
# ▶️ تشغيل
# =========================
print("Bot running (educational token) 🚀")
bot.infinity_polling()
