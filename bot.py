import telebot
from telebot import types
import subprocess
import os

BOT_TOKEN = "8516502699:AAG-yW_GxMjBYtmnD7WhRDnPcONQ1a_qguc"
bot = telebot.TeleBot(BOT_TOKEN)

user_links = {}

# =========================
# 🔥 yt-dlp تحميل
# =========================
def ytdlp_download(url, audio, chat_id, msg_id):
    try:
        bot.edit_message_text("⏳ جاري التحميل عبر yt-dlp...", chat_id, msg_id)

        ext = "mp3" if audio else "mp4"
        file = f"download_{chat_id}.{ext}"

        cmd = ["yt-dlp", url, "-o", file]

        if audio:
            cmd += ["-x", "--audio-format", "mp3"]
        else:
            cmd += ["-f", "mp4"]

        subprocess.run(cmd, check=True)
        return file

    except Exception as e:
        bot.edit_message_text(f"❌ فشل التحميل: {e}", chat_id, msg_id)
        return None

# =========================
# 🤖 أوامر
# =========================
@bot.message_handler(commands=["start"])
def start(m):
    bot.reply_to(
        m,
        "👋 أرسل الرابط\n"
        "🎬 فيديو أو 🎵 MP3\n"
        "⚡ يعمل على Railway بدون مشاكل"
    )

@bot.message_handler(func=lambda m: m.text.startswith("http"))
def link(m):
    user_links[m.chat.id] = m.text

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("🎬 فيديو", callback_data="v"),
        types.InlineKeyboardButton("🎵 MP3", callback_data="a")
    )

    bot.reply_to(m, "اختر الصيغة 👇", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data in ["v", "a"])
def process(c):
    chat_id = c.message.chat.id
    url = user_links.get(chat_id)

    bot.delete_message(chat_id, c.message.message_id)
    msg = bot.send_message(chat_id, "⏳ بدء التحميل...")

    path = ytdlp_download(url, c.data == "a", chat_id, msg.message_id)

    if path and os.path.exists(path):
        bot.edit_message_text("📤 رفع إلى تيليجرام...", chat_id, msg.message_id)

        with open(path, "rb") as f:
            if c.data == "a":
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
print("Bot running with yt-dlp only 🔥")
bot.infinity_polling()
