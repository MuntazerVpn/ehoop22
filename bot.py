import telebot
from telebot import types
import yt_dlp
import os
import time
import json
import datetime

# ==========================================
# ⚙️ الإعدادات
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
# 📥 دوال التحميل (بوضع الشاشة الذكية TV)
# ==========================================
def check_qualities(url):
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'geo_bypass': True,
            # ✅ استخدام هوية مشغل التلفاز
            'user_agent': 'Mozilla/5.0 (Linux; Adroid 11; Sony Bravia 4K TV Build/RP1A.200720.011) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.104 Safari/537.36',
            'extractor_args': {'youtube': {'player_client': ['tv', 'web_embedded']}},
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'youtube' in url or 'youtu.be' in url:
                formats = info.get('formats', [])
                resolutions = set()
                for f in formats:
                    if f.get('height'): resolutions.add(f.get('height'))
                return sorted(list(resolutions), reverse=True), info.get('title', 'Video')
            return ['Best'], info.get('title', 'Video')
    except Exception as e:
        return [], str(e)

def download_content(url, quality, chat_id, msg_id):
    try:
        # الإعدادات الذهبية لمحاكاة التلفاز ودمج الجودة
        ydl_opts = {
            'outtmpl': '%(title)s.%(ext)s', 
            'quiet': True, 
            'no_warnings': True,
            'nocheckcertificate': True,
            # ✅ محاكاة Sony Bravia 4K TV
            'user_agent': 'Mozilla/5.0 (Linux; Adroid 11; Sony Bravia 4K TV Build/RP1A.200720.011) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.104 Safari/537.36',
            'extractor_args': {'youtube': {'player_client': ['tv', 'web_embedded']}},
            'format': 'bestvideo+bestaudio/best', 
            'merge_output_format': 'mp4',
        }
        
        if quality == 'audio':
            ydl_opts.update({'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}]})
            bot.edit_message_text("جاري استخراج الصوت (TV Mode)... 🎵", chat_id, msg_id)
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
        bot.edit_message_text(f"❌ خطأ يوتيوب: {str(e)[:100]}", chat_id, msg_id)
        return None, None

# ==========================================
# 🤖 المعالجات
# ==========================================
@bot.message_handler(commands=['start'])
def welcome(message):
    bot.reply_to(message, "أهلاً بك! 👋\nأرسل رابط الفيديو للتحميل (تم تفعيل وضع TV Bypass).")

@bot.message_handler(func=lambda m: m.text.startswith('http'))
def get_link(m):
    user_id = m.from_user.id
    if not check_subscription(user_id):
        bot.reply_to(m, "⚠️ اشترك في القناة: @eshop_2")
        return

    wait = bot.reply_to(m, "جاري الفحص... 🔎")
    res, title_or_error = check_qualities(m.text)
    
    if not res: 
        bot.edit_message_text(f"❌ فشل: {title_or_error[:100]}", m.chat.id, wait.message_id)
        return
    
    user_urls[m.chat.id] = m.text
    markup = types.InlineKeyboardMarkup()
    if 'Best' in res:
        markup.add(types.InlineKeyboardButton("تحميل فيديو ✅", callback_data="q|Best"))
    else:
        btns = [types.InlineKeyboardButton(f"{r}p", callback_data=f"q|{r}") for r in res[:6]]
        markup.add(*btns)
    
    markup.add(types.InlineKeyboardButton("صوت (MP3) 🎵", callback_data="q|audio"))
    bot.edit_message_text(f"🎬 {title_or_error}", m.chat.id, wait.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith('q|'))
def process(c):
    user_id = c.message.chat.id
    url = user_urls.get(user_id)
    qual = c.data.split('|')[1]
    
    bot.delete_message(user_id, c.message.message_id)
    msg = bot.send_message(user_id, "جاري البدء... ⏳")
    
    path, title = download_content(url, qual, user_id, msg.message_id)
    
    if path and os.path.exists(path):
        try:
            bot.edit_message_text("جاري الرفع... 📤", user_id, msg.message_id)
            with open(path, 'rb') as f:
                if qual == 'audio': bot.send_audio(user_id, f, title=title)
                else: bot.send_video(user_id, f, caption=title)
            bot.delete_message(user_id, msg.message_id)
            os.remove(path)
        except Exception as e:
            bot.send_message(user_id, f"فشل الرفع: {e}")
            if os.path.exists(path): os.remove(path)

bot.infinity_polling()
