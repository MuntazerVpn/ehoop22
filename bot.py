import os
import glob
import subprocess
import telebot
from telebot import types

# ✅ تم إضافة التوكن الخاص بك هنا مباشرة
BOT_TOKEN = "8423770288:AAGPjI_9TZQXHUGj9bPn7yvORSwQQDHwGJA"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
user_links = {}

def cleanup(prefix: str):
    """حذف الملفات المؤقتة بعد الإرسال"""
    for f in glob.glob(prefix + ".*"):
        try:
            if os.path.isfile(f):
                os.remove(f)
        except:
            pass

def ytdlp_download(url: str, mode: str, chat_id: int, msg_id: int):
    """
    mode:
      a        => mp3
      v360     => mp4 <=360p
      v480     => mp4 <=480p
      v720     => mp4 <=720p
      v1080    => mp4 <=1080p
    """
    unique = f"dl_{chat_id}_{msg_id}"
    # نستخدم معرف فريد للملف لتجنب تداخل التحميلات
    outtmpl = f"{unique}.%(ext)s"

    try:
        bot.edit_message_text("⏳ جاري التحميل من المصدر...", chat_id, msg_id)
    except:
        pass

    cmd = ["yt-dlp", "--no-playlist", "--newline", url, "-o", outtmpl]

    # محاولة جلب العنوان
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
        # MP3 Settings
        cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
    else:
        # Video Settings
        if mode == "v360":
            h = 360
        elif mode == "v480":
            h = 480
        elif mode == "v720":
            h = 720
        else:
            h = 1080

        # أفضل صيغة متاحة حسب الجودة المطلوبة
        fmt = (
            f"bv*[ext=mp4][height<={h}]+ba[ext=m4a]/"
            f"b[ext=mp4][height<={h}]/"
            "b[ext=mp4]/best"
        )
        cmd += ["-f", fmt, "--merge-output-format", "mp4"]

    # تنفيذ الأمر
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        try:
            bot.edit_message_text(f"❌ خطأ في التحميل:\n<code>{err[-500:]}</code>", chat_id, msg_id)
        except:
            pass
        cleanup(unique)
        return None, None

    # البحث عن الملف الناتج
    files = [f for f in glob.glob(unique + ".*") if not f.endswith(".part")]
    if not files:
        try:
            bot.edit_message_text("❌ لم يتم العثور على ملف ناتج.", chat_id, msg_id)
        except:
            pass
        cleanup(unique)
        return None, None

    # ترتيب الملفات حسب الحجم (الأكبر غالباً هو المطلوب)
    files.sort(key=lambda p: os.path.getsize(p), reverse=True)
    return files[0], title

@bot.message_handler(commands=["start"])
def start(m):
    bot.reply_to(m, "👋 أرسل رابط الفيديو (يوتيوب، تيك توك، انستقرام)، ثم اختر الجودة.")

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
    kb.add(types.InlineKeyboardButton("🎵 تحويل صوت (MP3)", callback_data="a"))

    bot.reply_to(m, "اختر الجودة المطلوبة 👇", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data in ("v360", "v480", "v720", "v1080", "a"))
def process(c):
    chat_id = c.message.chat.id
    url = user_links.get(chat_id)

    if not url:
        bot.answer_callback_query(c.id, "❌ الرابط قديم، أرسله مرة أخرى.")
        return

    try:
        bot.delete_message(chat_id, c.message.message_id)
    except:
        pass

    msg = bot.send_message(chat_id, "📡 جاري بدء العملية...")
    unique = f"dl_{chat_id}_{msg.message_id}"

    try:
        path, title = ytdlp_download(url, c.data, chat_id, msg.message_id)

        if path and os.path.exists(path):
            bot.edit_message_text("📤 جاري الرفع إلى تيليجرام...", chat_id, msg.message_id)

            with open(path, "rb") as f:
                caption_text = title if title else "تم التحميل بواسطة البوت"
                
                if c.data == "a":
                    bot.send_audio(
                        chat_id, f, 
                        title=title[:50] if title else "Audio", 
                        caption="✅ تم التحويل لـ MP3"
                    )
                else:
                    bot.send_video(
                        chat_id, f, 
                        caption=f"🎥 {caption_text}\n✅ الجودة: {c.data.replace('v','')}"
                    )

            # حذف رسالة الانتظار
            try:
                bot.delete_message(chat_id, msg.message_id)
            except:
                pass
        else:
            # رسالة الخطأ تمت معالجتها داخل دالة التحميل
            pass

    except Exception as e:
        try:
            bot.edit_message_text(f"❌ خطأ غير متوقع: <code>{str(e)[:500]}</code>", chat_id, msg.message_id)
        except:
            pass
    finally:
        cleanup(unique)

print("✅ البوت يعمل الآن (Bot is running)...")
bot.infinity_polling(skip_pending=True)
