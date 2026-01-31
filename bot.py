import telebot
from telebot import types
import subprocess
import os
import glob

# =========================
# 🔑 توكن البوت
# =========================
BOT_TOKEN = "8516502699:AAEL92ZiIhErNZODRHDPlfiF1SfbpnJJ-ds"
bot = telebot.TeleBot(BOT_TOKEN)

user_links = {}

# =========================
# 🔥 yt-dlp تحميل
# =========================
def ytdlp_download(url, audio, chat_id, msg_id):
    try:
        bot.edit_message_text("⏳ جاري التحميل عبر yt-dlp...", chat_id, msg_id)

        base = f"download_{chat_id}"
        outtmpl = base + ".%(ext)s"

        cmd = ["yt-dlp", "--no-playlist", url, "-o", outtmpl]

        if audio:
            cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
        else:
            cmd += ["-f", "mp4"]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            bot.edit_message_text(
                "❌ خطأ أثناء التحميل:\n"
                f"{result.stderr[-1500:]}",
                chat_id, msg_id
            )
            return None

        if audio:
            files = glob.glob(base + ".mp3")
        else:
            files = [f for f in glob.glob(base + ".*") if not f.endswith(".part")]

        return files[0] if files else None

    except Exception as e:
        bot.edit_message_text(f"❌ فشل التحميل: {e}", chat_id, msg_id)
        return None

# =========================
# 🤖 أوامر البوت
# =========================
@bot.message_handler(commands=["start"])
def start(m):
    bot.reply_to(
        m,
        "👋 أرسل الرابط\n"
        "🎬 فيديو أو 🎵 MP3\n"
        "⚡ يعمل عبر yt-dlp"
    )

@bot.message_handler(func=lambda m: m.text and m.text.startswith("http"))
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
# ▶️ تشغيل البوت
# =========================
print("Bot running with yt-dlp 🔥")
bot.infinity_polling()
