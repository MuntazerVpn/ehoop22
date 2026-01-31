import telebot
from telebot import types
import yt_dlp
import os

# ⚠️ ضع التوكن الخاص بك هنا
BOT_TOKEN = '8513261810:AAENsuncE8EeW7JBB0fWrrO36uejFoZzTYw'
bot = telebot.TeleBot(BOT_TOKEN)

# دالة التحميل
def download_video(url):
    try:
        # إعدادات مخصصة لـ Railway (وضع الآيفون)
        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': '%(title)s.%(ext)s',
            'quiet': True,
            'extractor_args': {'youtube': {'player_client': ['ios']}}, # خداع اليوتيوب
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info), info.get('title', 'Video')
    except Exception as e:
        return None, str(e)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "أهلاً! أرسل رابط تيك توك، انستقرام، أو يوتيوب وسأقوم بتحميله. 🚀")

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    url = message.text
    if not url.startswith('http'): return

    msg = bot.reply_to(message, "جاري التحميل... ⏳")
    
    path, title = download_video(url)
    
    if path and os.path.exists(path):
        try:
            bot.edit_message_text("جاري الرفع... 📤", message.chat.id, msg.message_id)
            with open(path, 'rb') as video:
                bot.send_video(message.chat.id, video, caption=title)
            os.remove(path)
            bot.delete_message(message.chat.id, msg.message_id)
        except Exception as e:
            bot.edit_message_text(f"حجم الفيديو كبير جداً (أكثر من 50MB) ⚠️\nRailway لا يدعم رفع الملفات الضخمة.", message.chat.id, msg.message_id)
            os.remove(path)
    else:
        bot.edit_message_text(f"فشل التحميل ❌\n{title}", message.chat.id, msg.message_id)

print("Bot Started on Railway...")
bot.infinity_polling()