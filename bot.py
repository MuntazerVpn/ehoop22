import os, glob, subprocess, telebot
from telebot import types

# التوكن الخاص بك
BOT_TOKEN = "8423770288:AAGPjI_9TZQXHUGj9bPn7yvORSwQQDHwGJA"
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
user_links = {}

def cleanup(match):
    """حذف الملفات المؤقتة"""
    for f in glob.glob(f"{match}*"):
        try: os.remove(f)
        except: pass

@bot.message_handler(commands=["start"])
def start(m):
    bot.reply_to(m, "👋 أرسل الرابط مباشرة.")

@bot.message_handler(func=lambda m: m.text and m.text.startswith("http"))
def link(m):
    user_links[m.chat.id] = m.text.strip()
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("360p", callback_data="v360"),
        types.InlineKeyboardButton("720p", callback_data="v720"),
        types.InlineKeyboardButton("1080p", callback_data="v1080"),
        types.InlineKeyboardButton("🎵 MP3", callback_data="a")
    )
    bot.reply_to(m, "اختر الجودة:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: True)
def process(c):
    chat_id, msg_id = c.message.chat.id, c.message.message_id
    url = user_links.get(chat_id)
    if not url: return bot.answer_callback_query(c.id, "❌ الرابط انتهى")

    bot.edit_message_text("⏳ جاري التحميل...", chat_id, msg_id)
    unique = f"dl_{chat_id}_{msg_id}"
    
    # إعداد الأمر
    cmd = ["yt-dlp", "--no-playlist", url, "-o", f"{unique}.%(ext)s"]
    if c.data == "a":
        cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
    else:
        h = c.data.replace('v', '')
        # تحميل أفضل فيديو بارتفاع محدد + أفضل صوت ودمجهم
        cmd += ["-f", f"bv*[height<={h}]+ba/b[height<={h}]/best", "--merge-output-format", "mp4"]

    try:
        subprocess.run(cmd, check=True) # التحميل
        files = glob.glob(f"{unique}.*")
        
        if files:
            file_path = max(files, key=os.path.getsize) # الملف الأكبر هو الهدف
            bot.edit_message_text("📤 جاري الإرسال...", chat_id, msg_id)
            
            with open(file_path, "rb") as f:
                if c.data == "a":
                    bot.send_audio(chat_id, f, caption="✅ تم التحويل")
                else:
                    bot.send_video(chat_id, f, caption="✅ تم التحميل")
            bot.delete_message(chat_id, msg_id)
        else:
            bot.edit_message_text("❌ فشل التحميل", chat_id, msg_id)

    except Exception as e:
        print(e)
        bot.edit_message_text("❌ حدث خطأ أثناء المعالجة", chat_id, msg_id)
    finally:
        cleanup(unique)

print("🚀 البوت يعمل...")
bot.infinity_polling(skip_pending=True)
