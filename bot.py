import telebot
from telebot import types
import yt_dlp
import os
import time
import json
import datetime

# ==========================================
# ⚙️ الإعدادات (iShop Bot)
# ==========================================
BOT_TOKEN = '8516502699:AAG-yW_GxMjBYtmnD7WhRDnPcONQ1a_qguc'
bot = telebot.TeleBot(BOT_TOKEN)

OWNER_ID = 8513261810
CHANNEL_USERNAME = "@eshop_2" 
DB_FILE = "users_db.json"

user_urls = {}

# ==========================================
# 📂 إدارة قاعدة البيانات
# ==========================================
def load_db():
    try:
        with open(DB_FILE, 'r') as f: return json.load(f)
    except: return {}

def save_db(data):
    with open(DB_FILE, 'w') as f: json.dump(data, f, indent=4)

def init_user(user_id, db):
    str_id = str(user_id)
    today = str(datetime.date.today())
    if str_id not in db:
        db[str_id] = {"joined_date": str(datetime.datetime.now()), "last_use": 0, "data_usage": 0, "usage_date": today}
        return True, db
    return False, db

def check_subscription(user_id):
    if user_id == OWNER_ID: return True
    try:
        status = bot.get_chat_member(CHANNEL_USERNAME, user_id).status
        return status in ['creator', 'administrator', 'member']
    except: return True 

# ==========================================
# 📥 دوال التحميل (تحديث التجاوز 2026)
# ==========================================
def download_content(url, quality, chat_id, msg_id):
    try:
        ydl_opts = {
            'outtmpl': '%(title)s.%(ext)s', 
            'quiet': True, 
            'no_warnings': True,
            'nocheckcertificate': True,
            # ✅ استخدام User-Agent لمتصفح Chrome حديث جداً (نظام ويندوز)
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            # ✅ إضافة رؤوس طلبات لمحاكاة تصفح حقيقي
            'http_headers': {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Sec-Fetch-Mode': 'navigate',
            },
            # ✅ استخدام مشغل الويب المحمول (mweb) لتجاوز قيود DRM
            'extractor_args': {'youtube': {'player_client': ['mweb', 'web_embedded']}},
            'format': 'bestvideo+bestaudio/best', 
            'merge_output_format': 'mp4',
            'ignoreerrors': False,
        }
        
        if quality == 'audio':
            ydl_opts.update({'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}]})
            bot.edit_message_text("جاري استخراج الصوت... 🎵", chat_id, msg_id)
        else:
            bot.edit_message_text(f"جاري جلب الفيديو بجودة {quality}p... 🚀", chat_id, msg_id)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            f = ydl.prepare_filename(info)
            
            base, ext = os.path.splitext(f)
            if quality == 'audio': f = base + '.mp3'
            else:
                if os.path.exists(base + '.mp4'): f = base + '.mp4'
                elif os.path.exists(base + '.mkv'): f = base + '.mkv'

            return f, info.get('title', 'media')
            
    except Exception as e:
        err = str(e)
        # ✅ رسائل خطأ واضحة للمستخدم
        if "403" in err:
            msg = "❌ السيرفر محظور حالياً من يوتيوب. يرجى المحاولة لاحقاً."
        elif "DRM" in err:
            msg = "⚠️ هذا الفيديو محمي ولا يمكن تحميله برمجياً."
        else:
            msg = f"❌ فشل: {err[:50]}..."
        
        bot.edit_message_text(msg, chat_id, msg_id)
        return None, None

# (استخدم بقية المعالجات من الكود الأصلي)
