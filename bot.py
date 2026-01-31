import telebot
from telebot import types
import subprocess
import os
import glob

# =========================
# 🔑 توكن البوت الجديد (تم التحديث)
# =========================
BOT_TOKEN = "8516502699:AAEL92ZiIhErNZODRHDPlfiF1SfbpnJJ-ds"
bot = telebot.TeleBot(BOT_TOKEN)

user_links = {}

# =========================
# 🔥 وظيفة التحميل المحسنة
# =========================
def ytdlp_download(url, audio, chat_id, msg_id):
    try:
        bot.edit_message_text("⏳ جاري معالجة الرابط والتحميل...", chat_id, msg_id)

        # توليد اسم ملف فريد لمنع التداخل
        unique_name = f"dl_{chat_id}_{msg_id}"
        outtmpl = f"{unique_name}.%(ext)s"

        # إعدادات yt-dlp
        # --extract-audio تحول أي فيديو أو صوت إلى صيغة صوتية فقط
        cmd = ["yt-dlp", "--no-playlist", url, "-o", outtmpl]

        if audio:
            # تحويل أي مصدر (Opus, Vorbis, AAC) إلى MP3 حصراً
            cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
        else:
            # تحميل فيديو بصيغة MP4
            cmd += ["-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            bot.edit_message_text(f"❌ خطأ:\n{result.stderr[-200:]}", chat_id, msg_id)
            return None

        # البحث عن الملف الناتج (بأي امتداد)
        files = glob.glob(f"{unique_name}.*")
        final_file = [f for f in files if not f.endswith(".part")]
        
        return final_file[0] if final_file else None

    except Exception as e:
        bot.edit_message_text(f"❌ فشل: {e}", chat_id, msg_id)
        return None

# =========================
# 🤖 أوامر البوت
# =========================
@bot.message_handler(commands=["start"])
def start(m):
    bot.reply_to(
        m,
        "👋 أهلاً بك! أرسل رابط الفيديو (YouTube, TikTok, Instagram...)\n"
        "وسأقوم بتحويله لك إلى فيديو أو ملف صوتي MP3 بجودة عالية."
    )

@bot.message_handler(func=lambda m: m.text and m.text.startswith("http"))
def link(m):
    user_links[m.chat.id] = m.text
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("🎬 فيديو (MP4)", callback_data="v"),
        types.InlineKeyboardButton("🎵 صوت (MP3)", callback_data="a")
    )
    bot.reply_to(m, "اختر الصيغة المطلوبة 👇", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data in ["v", "a"])
def process(c):
    chat_id = c.message.chat.id
    url = user_links.get(chat_id)

    if not url:
        bot.answer_callback_query(c.id, "❌ انتهت صلاحية الرابط، أرسله مجدداً.")
        return

    bot.delete_message(chat_id, c.message.message_id)
    msg = bot.send_message(chat_id, "📡 جاري التحميل من المصدر...")

    path = ytdlp_download(url, c.data == "a", chat_id, msg.message_id)

    if path and os.path.exists(path):
        bot.edit_message_text("📤 جاري الرفع إلى تيليجرام...", chat_id, msg.message_id)

        try:
            with open(path, "rb") as f:
                if c.data == "a":
                    bot.send_audio(chat_id, f, caption="✅ تم التحويل بنجاح عبر @YourBot")
                else:
                    bot.send_video(chat_id, f, caption="✅ تم التحميل بنجاح")
            
            bot.delete_message(chat_id, msg.message_id)
        except Exception as e:
            bot.edit_message_text(f"❌ فشل الرفع: {e}", chat_id, msg.message_id)
        
        # تنظيف الملفات بعد الإرسال
        if os.path.exists(path):
            os.remove(path)
    else:
        bot.edit_message_text("❌ عذراً، لم أتمكن من تحميل الملف.", chat_id, msg.message_id)

# =========================
# ▶️ تشغيل البوت
# =========================
print("✅ البوت يعمل الآن...")
bot.infinity_polling()
