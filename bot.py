import os
import glob
import subprocess
import shutil
import telebot
from telebot import types

# ✅ التوكن الخاص بك
BOT_TOKEN = "8423770288:AAGPjI_9TZQXHUGj9bPn7yvORSwQQDHwGJA"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
user_links = {}

def cleanup(prefix: str):
    """حذف الملفات المؤقتة بشكل آمن"""
    try:
        for f in glob.glob(f"{prefix}*"):
            if os.path.isfile(f):
                os.remove(f)
    except Exception as e:
        print(f"⚠️ Error cleaning up: {e}")

def get_ffmpeg_path():
    """البحث عن مسار FFmpeg تلقائياً في النظام"""
    path = shutil.which("ffmpeg")
    if path:
        return path
    
    # مسارات شائعة احتياطية (Linux/Windows)
    common_paths = [
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "C:\\ffmpeg\\bin\\ffmpeg.exe",
        "ffmpeg.exe"
    ]
    for p in common_paths:
        if os.path.exists(p):
            return p
    return None

def ytdlp_download(url: str, mode: str, chat_id: int, msg_id: int):
    """
    تحميل الفيديو أو الصوت باستخدام yt-dlp مع إعدادات متقدمة
    """
    unique = f"dl_{chat_id}_{msg_id}"
    outtmpl = f"{unique}.%(ext)s"

    try:
        bot.edit_message_text("⏳ جاري المعالجة والتحميل...", chat_id, msg_id)
    except:
        pass

    # تجهيز الأمر الأساسي
    cmd = [
        "yt-dlp", 
        "--no-playlist", 
        "--newline", 
        "--socket-timeout", "30",
        "--no-mtime",  # عدم استخدام وقت الملف الأصلي لتسهيل الحذف
        url, 
        "-o", outtmpl
    ]

    # ✅ إضافة مسار FFmpeg إذا وجد
    ffmpeg_loc = get_ffmpeg_path()
    if ffmpeg_loc:
        cmd += ["--ffmpeg-location", ffmpeg_loc]
    else:
        print("⚠️ Warning: FFmpeg not found! MP3 conversion might fail.")

    # محاولة جلب العنوان (Title)
    title = "Media File"
    try:
        t = subprocess.run(
            ["yt-dlp", "--no-playlist", "--print", "%(title)s", url],
            capture_output=True, text=True, encoding='utf-8', errors='ignore'
        )
        if t.returncode == 0:
            title = (t.stdout or "").strip()[:100]
    except:
        pass

    # إعدادات الصيغة (صوت أو فيديو)
    if mode == "a":
        # MP3 Settings
        if not ffmpeg_loc:
             try:
                 bot.edit_message_text("⚠️ خطأ: أداة التحويل (FFmpeg) غير مثبتة في السيرفر.", chat_id, msg_id)
             except: pass
             return None, None
             
        cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
    else:
        # Video Settings (Best MP4 compatible format)
        resolutions = {
            "v360": "360",
            "v480": "480",
            "v720": "720",
            "v1080": "1080"
        }
        h = resolutions.get(mode, "720")
        
        # صيغة ذكية تدمج أفضل فيديو مع أفضل صوت وتخرج MP4
        fmt = (
            f"bv*[ext=mp4][height<={h}]+ba[ext=m4a]/"
            f"b[ext=mp4][height<={h}]/"
            "b[ext=mp4]/best"
        )
        cmd += ["-f", fmt, "--merge-output-format", "mp4"]

    # تنفيذ الأمر
    print(f"🔄 Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
    
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        print(f"❌ Error: {err}")
        try:
            bot.edit_message_text(f"❌ حدث خطأ أثناء التحميل:\n<pre>{err[-300:]}</pre>", chat_id, msg_id)
        except:
            pass
        cleanup(unique)
        return None, None

    # البحث عن الملف الناتج (تجاهل الملفات المؤقتة .part .ytdl)
    files = [f for f in glob.glob(f"{unique}.*") if not f.endswith(('.part', '.ytdl', '.webp', '.jpg'))]
    
    if not files:
        try:
            bot.edit_message_text("❌ اكتملت العملية لكن لم يتم العثور على الملف.", chat_id, msg_id)
        except:
            pass
        cleanup(unique)
        return None, None

    # نختار أكبر ملف (غالباً هو الفيديو/الصوت النهائي)
    files.sort(key=lambda p: os.path.getsize(p), reverse=True)
    return files[0], title

# --- Handlers ---

@bot.message_handler(commands=["start"])
def start(m):
    welcome_text = (
        "👋 <b>أهلاً بك في بوت التحميل!</b>\n\n"
        "أرسل رابطاً من (TikTok, Instagram, YouTube, Facebook)\n"
        "وسأقوم بتحميله لك بالجودة التي تختارها."
    )
    bot.reply_to(m, welcome_text)

@bot.message_handler(func=lambda m: m.text and m.text.strip().startswith(("http://", "https://")))
def link_handler(m):
    user_links[m.chat.id] = m.text.strip()

    kb = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton("🎬 360p", callback_data="v360"),
        types.InlineKeyboardButton("🎬 480p", callback_data="v480"),
        types.InlineKeyboardButton("🎬 720p", callback_data="v720"),
        types.InlineKeyboardButton("🎬 1080p", callback_data="v1080"),
        types.InlineKeyboardButton("🎵 صوت فقط (MP3)", callback_data="a")
    ]
    kb.add(*buttons)

    bot.reply_to(m, "👇 اختر الجودة المطلوبة:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data in ("v360", "v480", "v720", "v1080", "a"))
def callback_handler(c):
    chat_id = c.message.chat.id
    url = user_links.get(chat_id)

    if not url:
        bot.answer_callback_query(c.id, "❌ الرابط انتهى، أرسله مجدداً.")
        return

    # حذف القائمة
    try:
        bot.delete_message(chat_id, c.message.message_id)
    except:
        pass

    msg = bot.send_message(chat_id, "📡 جاري الاتصال بالسيرفر...")
    unique = f"dl_{chat_id}_{msg.message_id}"

    try:
        path, title = ytdlp_download(url, c.data, chat_id, msg.message_id)

        if path and os.path.exists(path):
            bot.edit_message_text("📤 جاري الرفع إليك...", chat_id, msg.message_id)

            with open(path, "rb") as f:
                caption_text = f"🎥 <b>{title}</b>" if title else "✅ تم التحميل"
                
                if c.data == "a":
                    bot.send_audio(
                        chat_id, f, 
                        title=title[:50] if title else "Audio", 
                        performer="Bot Downloader",
                        caption="🎧 تم استخراج الصوت بنجاح"
                    )
                else:
                    bot.send_video(
                        chat_id, f, 
                        caption=f"{caption_text}\n💿 الجودة: {c.data.replace('v','')}",
                        supports_streaming=True
                    )

            # تنظيف وحذف رسالة الانتظار
            try:
                bot.delete_message(chat_id, msg.message_id)
            except:
                pass
    except Exception as e:
        print(f"Main Error: {e}")
        try:
            bot.edit_message_text("❌ حدث خطأ غير متوقع في البوت.", chat_id, msg.message_id)
        except:
            pass
    finally:
        cleanup(unique)

print("✅ Bot Started successfully...")
bot.infinity_polling(skip_pending=True)
