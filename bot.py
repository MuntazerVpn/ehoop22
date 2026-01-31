import os
import glob
import subprocess
import telebot
from telebot import types

# =========================
# 🔑 توكن البوت الجديد الخاص بك
# =========================
BOT_TOKEN = "8423770288:AAGPjI_9TZQXHUGj9bPn7yvORSwQQDHwGJA"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
user_links = {}

def cleanup(prefix: str):
    """حذف الملفات المؤقتة بعد الإرسال لتوفير مساحة السيرفر"""
    for f in glob.glob(prefix + ".*"):
        try:
            if os.path.isfile(f):
                os.remove(f)
        except:
            pass

def ytdlp_download(url: str, mode: str, chat_id: int, msg_id: int):
    """
    تحميل المحتوى باستخدام yt-dlp
    mode: 'a' للصوت، أو 'v' للجودات (360, 480, 720, 1080)
    """
    unique = f"dl_{chat_id}_{msg_id}"
    outtmpl = f"{unique}.%(ext)s"

    bot.edit_message_text("⏳ جاري التحميل والمعالجة...", chat_id, msg_id)

    # الأوامر الأساسية
    cmd = ["yt-dlp", "--no-playlist", "--newline", url, "-o", outtmpl]

    # جلب عنوان المقطع
    title = "فيديو"
    try:
        t = subprocess.run(
            ["yt-dlp", "--no-playlist", "--print", "%(title)s", url],
            capture_output=True, text=True
        )
        if t.returncode == 0:
            title = (t.stdout or "").strip()[:100]
    except:
        pass

    if mode == "a":
        # إعدادات تحويل الصوت لـ MP3 بأعلى جودة
        cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
    else:
        # تحديد الجودة
        if mode == "v360": h = 360
        elif mode == "v480": h = 480
        elif mode == "v720": h = 720
        else: h = 1080

        fmt = (
            f"bv*[ext=mp4][height<={h}]+ba[ext=m4a]/"
            f"b[ext=mp4][height<={h}]/"
            "b[ext=mp4]/best"
        )
        cmd += ["-f", fmt, "--merge-output-format", "mp4"]

    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        bot.edit_message_text(f"❌ خطأ:\n<code>{err[-500:]}</code>", chat_id, msg_id)
        cleanup(unique)
        return None, None

    # البحث عن الملف الناتج
    files = [f for f in glob.glob(unique + ".*") if not f.endswith(".part")]
    if not files:
        bot.edit_message_text("❌ لم يتم العثور على الملف.", chat_id, msg_id)
        cleanup(unique)
        return None, None

    return files[0], title

@bot.message_handler(commands=["start"])
def start(m):
    bot.reply_to(m, "<b>مرحباً بك!</b> 🤖\n\nأرسل رابط المقطع وسأقوم بتحميله لك بالجودة التي تختارها.")

@bot.message_handler(func=lambda m: m.text and m.text.startswith(("http", "https")))
def link(m):
    user_links[m.chat.id] = m.text.strip()

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🎬 360p", callback_data="v360"),
        types.InlineKeyboardButton("🎬 480p", callback_data="v480"),
        types.InlineKeyboardButton("🎬 720p", callback_data="v720"),
        types.InlineKeyboardButton("🎬 1080p", callback_data="v1080"),
    )
    kb.add(types.InlineKeyboardButton("🎵 بصيغة MP3", callback_data="a"))

    bot.reply_to(m, "اختر الجودة المطلوبة 👇", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data in ("v360", "v480", "v720", "v1080", "a"))
def process(c):
    chat_id = c.message.chat.id
    url = user_links.get(chat_id)

    if not url:
        bot.answer_callback_query(c.id, "⚠️ الرابط مفقود، أرسله مجدداً.")
        return

    bot.delete_message(chat_id, c.message.message_id)
    msg = bot.send_message(chat_id, "📡 جاري التحميل...")
    unique = f"dl_{chat_id}_{msg.message_id}"

    try:
        path, title = ytdlp_download(url, c.data, chat_id, msg.message_id)

        if path and os.path.exists(path):
            bot.edit_message_text("📤 جاري الرفع...", chat_id, msg.message_id)

            with open(path, "rb") as f:
                if c.data == "a":
                    bot.send_audio(chat_id, f, title=title, caption=f"✅ {title}")
                else:
                    bot.send_video(chat_id, f, caption=f"✅ {title}\nجودة: {c.data.replace('v','')}p")

            bot.delete_message(chat_id, msg.message_id)
        else:
            pass 
    except Exception as e:
        bot.send_message(chat_id, f"❌ خطأ غير متوقع: {str(e)[:200]}")
    finally:
        cleanup(unique)

# =========================
# ▶️ تشغيل البوت
# =========================
print("✅ البوت يعمل الآن بالتوكن الجديد!")
bot.infinity_polling(skip_pending=True)

⚠️ تنبيه هام: بما أنك نشرت التوكن هنا، فإنه يعتبر مكشوفاً للعامة. يفضل دائماً استخدامه في بيئة خاصة، وإذا لاحظت أي تصرف غريب في البوت، قم بتغيير التوكن من خلال @BotFather.
هل هناك أي ميزة إضافية تود إضافتها للبوت؟

