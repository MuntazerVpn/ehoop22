import os
import re
import glob
import shutil
import subprocess
from pathlib import Path

import telebot
from telebot import types

# =========================
# 🔑 تم وضع توكن بوتك هنا
# =========================
BOT_TOKEN = "8516502699:AAEL92ZiIhErNZODRHDPlfiF1SfbpnJJ-ds"
bot = telebot.TeleBot(BOT_TOKEN)

user_links = {}

# الصيغ اللي نعرضها للمستخدم
AUDIO_FORMATS = ["mp3", "m4a", "opus", "wav", "flac"]

def safe_dirname(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", s)

def run_cmd(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)

# =========================
# 🔥 yt-dlp Download (Audio)
# =========================
def ytdlp_download_audio(url: str, audio_format: str, chat_id: int, msg_id: int):
    # إنشاء مجلد مؤقت لكل عملية تحميل لمنع تداخل الملفات
    workdir = Path(f"job_{safe_dirname(str(chat_id))}_{msg_id}")
    workdir.mkdir(parents=True, exist_ok=True)

    try:
        bot.edit_message_text("⏳ جاري استخراج وتحويل الصوت...", chat_id, msg_id)

        # نكتب اسم ثابت داخل مجلد العمل
        outtmpl = str(workdir / "audio.%(ext)s")

        cmd = [
            "yt-dlp",
            "--no-playlist",
            "-x",
            "--audio-format", audio_format,
            "--audio-quality", "0",
            "-o", outtmpl,
            url,
        ]

        result = run_cmd(cmd)
        if result.returncode != 0:
            error_msg = (result.stderr or result.stdout)[-500:]
            bot.edit_message_text(f"❌ خطأ أثناء التحميل:\n`{error_msg}`", chat_id, msg_id)
            return None, workdir

        # البحث عن الملف الناتج
        files = [p for p in workdir.glob("audio.*") if not str(p).endswith(".part")]
        if not files:
            bot.edit_message_text("❌ لم يتم العثور على الملف الناتج", chat_id, msg_id)
            return None, workdir

        return str(files[0]), workdir

    except Exception as e:
        bot.edit_message_text(f"❌ فشل التحميل: {e}", chat_id, msg_id)
        return None, workdir

def cleanup_dir(workdir: Path):
    try:
        shutil.rmtree(workdir, ignore_errors=True)
    except:
        pass

# =========================
# 🤖 Bot Commands
# =========================
@bot.message_handler(commands=["start"])
def start(m):
    bot.reply_to(
        m,
        "👋 أهلاً بك في بوت تحميل الصوتيات!\n\n"
        "أرسل رابط (يوتيوب، تيك توك، إلخ) وسأقوم بتحويله لأي صيغة تختارها.\n"
        "⚡ مدعوم بواسطة yt-dlp"
    )

@bot.message_handler(func=lambda m: m.text and m.text.startswith("http"))
def link(m):
    user_links[m.chat.id] = m.text

    # إنشاء أزرار اختيار الصيغة
    kb = types.InlineKeyboardMarkup(row_width=3)
    btns = [types.InlineKeyboardButton(f"🎵 {fmt.upper()}", callback_data=f"a:{fmt}") for fmt in AUDIO_FORMATS]
    kb.add(*btns)

    bot.reply_to(m, "اختر صيغة الصوت التي تريد تحميلها 👇", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("a:"))
def process_audio(c):
    chat_id = c.message.chat.id
    url = user_links.get(chat_id)
    
    if not url:
        bot.answer_callback_query(c.id, "⚠️ الرجاء إرسال الرابط مرة أخرى")
        return

    audio_format = c.data.split(":", 1)[1]

    bot.delete_message(chat_id, c.message.message_id)
    msg = bot.send_message(chat_id, f"🚀 بدأنا تحويل الرابط إلى {audio_format.upper()}...")

    path, workdir = ytdlp_download_audio(url, audio_format, chat_id, msg.message_id)

    if path and os.path.exists(path):
        bot.edit_message_text("📤 جاري الرفع إلى تيليجرام...", chat_id, msg.message_id)

        try:
            # التحقق من الصيغ التي يدعمها مشغل تيليجرام كصوت
            send_as_audio = audio_format in ["mp3", "m4a", "opus", "wav"]
            with open(path, "rb") as f:
                if send_as_audio:
                    bot.send_audio(chat_id, f, caption=f"✅ تم التحويل إلى {audio_format.upper()}")
                else:
                    bot.send_document(chat_id, f, caption=f"✅ تم التحميل بصيغة {audio_format.upper()}")
            
            bot.delete_message(chat_id, msg.message_id)
        except Exception as e:
            bot.edit_message_text(f"❌ خطأ أثناء الرفع: {e}", chat_id, msg.message_id)
    else:
        # الرسالة تظهر فعلياً داخل ytdlp_download_audio في حال الفشل
        pass

    cleanup_dir(Path(workdir))

# =========================
# ▶️ Run
# =========================
print("✅ البوت يعمل الآن.. بانتظار الروابط 🔥")
bot.infinity_polling()
