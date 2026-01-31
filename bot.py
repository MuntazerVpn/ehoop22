import os
import glob
import subprocess
import telebot
from telebot import types

# =========================
# 🔑 توكن بوتك الخاص
# =========================
BOT_TOKEN = "8516502699:AAEL92ZiIhErNZODRHDPlfiF1SfbpnJJ-ds"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
user_links = {}

def cleanup(prefix: str):
    """تنظيف الملفات المؤقتة بعد الانتهاء"""
    for f in glob.glob(prefix + ".*"):
        try:
            if os.path.isfile(f):
                os.remove(f)
        except:
            pass

def ytdlp_download(url: str, mode: str, chat_id: int, msg_id: int):
    """
    تحميل المحتوى باستخدام yt-dlp
    mode: (a) للصوت، أو جودات الفيديو (v360, v480, v720, v1080)
    """
    unique = f"dl_{chat_id}_{msg_id}"
    outtmpl = f"{unique}.%(ext)s"

    bot.edit_message_text("⏳ جاري التحميل والمعالجة...", chat_id, msg_id)

    cmd = ["yt-dlp", "--no-playlist", "--newline", url, "-o", outtmpl]

    # محاولة جلب عنوان الفيديو
    title = None
    try:
        t = subprocess.run(
            ["yt-dlp", "--no-playlist", "--print", "%(title)s", url],
            capture_output=True, text=True
        )
        if t.returncode == 0:
            title = (t.stdout or "").strip()[:120]
    except:
        pass

    if mode == "a":
        # إعدادات تحويل الصوت إلى MP3 بأعلى جودة
        cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
    else:
        # تحديد جودة الفيديو المطلوبة
        if mode == "v360": h = 360
        elif mode == "v480": h = 480
        elif mode == "v720": h = 720
        else: h = 1080

        # اختيار أفضل صيغة MP4 متاحة تحت الجودة المحددة
        fmt = (
            f"bv*[ext=mp4][height<={h}]+ba[ext=m4a]/"
            f"b[ext=mp4][height<={h}]/"
            "b[ext=mp4]/best"
        )
        cmd += ["-f", fmt, "--merge-output-format", "mp4"]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        bot.edit_message_text(f"❌ خطأ في النظام:\n<code>{err[-1200:]}</code>", chat_id, msg_id)
        cleanup(unique)
        return None, None

    # العثور على الملف النهائي
    files = [f for f in glob.glob(unique + ".*") if not f.endswith(".part")]
    if not files:
        bot.edit_message_text("❌ فشل العثور على الملف الناتج.", chat_id, msg_id)
        cleanup(unique)
        return None, None

    files.sort(key=lambda p: os.path.getsize(p), reverse=True)
    return files[0], title

@bot.message_handler(commands=["start"])
def start(m):
    bot.reply_to(m, "👋 أهلاً بك! أرسل رابط الفيديو، ثم اختر الجودة المطلوبة أو تحويله إلى MP3.")

@bot.message_handler(func=lambda m: m.text and m.text.startswith(("http://", "https://")))
def link(m):
    user_links[m.chat.id] = m.text.strip()

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🎬 360p", callback_data="v360"),
        types.InlineKeyboardButton("🎬 480p", callback_data="v480"),
        types.InlineKeyboardButton("🎬 720p", callback_data="v720"),
        types.InlineKeyboardButton("🎬 1080p", callback_data="v1080"),
    )
    kb.add(types.InlineKeyboardButton("🎵 تحويل إلى MP3", callback_data="a"))

    bot.reply_to(m, "اختر الجودة أو الصيغة 👇", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data in ("v360", "v480", "v720", "v1080", "a"))
def process(c):
    chat_id = c.message.chat.id
    url = user_links.get(chat_id)

    if not url:
        bot.answer_callback_query(c.id, "⚠️ الرابط مفقود، أعد إرساله.")
        return

    try:
        bot.delete_message(chat_id, c.message.message_id)
    except:
        pass

    msg = bot.send_message(chat_id, "📡 جاري جلب البيانات...")
    unique = f"dl_{chat_id}_{msg.message_id}"

    try:
        path, title = ytdlp_download(url, c.data, chat_id, msg.message_id)

        if path and os.path.exists(path):
            bot.edit_message_text("📤 جاري رفع الملف إلى تيليجرام...", chat_id, msg.message_id)

            with open(path, "rb") as f:
                if c.data == "a":
                    bot.send_audio(chat_id, f, title=title or "Audio", caption="✅ تم التحويل إلى MP3 بنجاح")
                else:
                    bot.send_video(chat_id, f, caption=f"✅ تم تحميل الفيديو بجودة {c.data.replace('v','')}p")

            try:
                bot.delete_message(chat_id, msg.message_id)
            except:
                pass
        else:
            # رسالة الخطأ يتم إرسالها من داخل دالة التحميل
            pass

    except Exception as e:
        try:
            bot.edit_message_text(f"❌ حدث خطأ غير متوقع: <code>{str(e)[:1000]}</code>", chat_id, msg.message_id)
        except:
            pass
    finally:
        cleanup(unique)

# =========================
# ▶️ تشغيل البوت
# =========================
print("✅ البوت يعمل الآن بكفاءة عالية 🔥")
bot.infinity_polling(skip_pending=True)
