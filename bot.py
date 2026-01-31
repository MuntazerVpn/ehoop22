import telebot
from telebot import types
import yt_dlp
import os
import time
import json
import datetime

# ==========================================
# ⚙️ الإعدادات (التوكن الجديد الخاص بك)
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
    if db[str_id].get("usage_date") != today:
        db[str_id]["data_usage"] = 0
        db[str_id]["usage_date"] = today
    return False, db

def check_subscription(user_id):
    if user_id == OWNER_ID: return True
    try:
        status = bot.get_chat_member(CHANNEL_USERNAME, user_id).status
        return status in ['creator', 'administrator', 'member']
    except: return True 

# ==========================================
# 📥 دوال التحميل المحسنة
# ==========================================
def check_qualities(url):
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'geo_bypass': True,
            'extractor_args': {'youtube': {'player_client': ['ios', 'android']}},
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
        # إعدادات تضمن دمج الصوت والصورة بجودة عالية
        ydl_opts = {
            'outtmpl': '%(title)s.%(ext)s', 
            'quiet': True, 
            'no_warnings': True,
            'extractor_args': {'youtube': {'player_client': ['android', 'ios']}},
            'format': 'bestvideo+bestaudio/best', 
            'merge_output_format': 'mp4',
        }
        
        if quality == 'audio':
            ydl_opts.update({'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}]})
            bot.edit_message_text("جاري تحميل الصوت... 🎵", chat_id, msg_id)
        else:
            bot.edit_message_text(f"جاري تحضير الفيديو... 🚀", chat_id, msg_id)

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
        bot.edit_message_text(f"❌ حدث خطأ: {str(e)[:100]}", chat_id, msg_id)
        return None, None

# ==========================================
# 🤖 المعالجات
# ==========================================
@bot.message_handler(commands=['start'])
def welcome(message):
    user_id = message.from_user.id
    db = load_db()
    init_user(user_id, db)
    save_db(db)
    bot.reply_to(message, "أهلاً بك! 👋\nأرسل رابط فيديو من يوتيوب، تيك توك، أو انستقرام وسأقوم بتحميله لك.")

@bot.message_handler(func=lambda m: m.text.startswith('http'))
def get_link(m):
    user_id = m.from_user.id
    if not check_subscription(user_id):
        bot.reply_to(m, "⚠️ عذراً، يجب عليك الاشتراك في القناة أولاً: @eshop_2")
        return

    wait = bot.reply_to(m, "جاري الفحص... 🔎")
    res, title_or_error = check_qualities(m.text)
    
    if not res: 
        bot.edit_message_text(f"❌ خطأ: الرابط غير مدعوم أو محمي.", m.chat.id, wait.message_id)
        return
    
    user_urls[m.chat.id] = m.text
    markup = types.InlineKeyboardMarkup()
    if 'Best' in res:
        markup.add(types.InlineKeyboardButton("تحميل فيديو ✅", callback_data="q|Best"))
    else:
        # عرض أول 6 جودات فقط لعدم ازدحام الأزرار
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
    msg = bot.send_message(user_id, "جاري المعالجة... ⏳")
    
    path, title = download_content(url, qual, user_id, msg.message_id)
    
    if path and os.path.exists(path):
        try:
            bot.edit_message_text("جاري الرفع إلى تيليجرام... 📤", user_id, msg.message_id)
            with open(path, 'rb') as f:
                if qual == 'audio': bot.send_audio(user_id, f, title=title)
                else: bot.send_video(user_id, f, caption=title)
            bot.delete_message(user_id, msg.message_id)
            os.remove(path)
        except Exception as e:
            bot.send_message(user_id, f"فشل الرفع: {e}")
            if os.path.exists(path): os.remove(path)

bot.infinity_polling()
