import telebot
from telebot import types
import requests
import os
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
# 📥 دالة التحميل عبر Cobalt API
# ==========================================
def download_content(url, quality, chat_id, msg_id):
    try:
        # رابط الجسر الخاص بـ Cobalt
        api_url = "https://api.cobalt.tools/api/json"
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        payload = {
            "url": url,
            "vQuality": "720", 
            "isAudioOnly": True if quality == 'audio' else False,
            "filenameStyle": "pretty"
        }
        
        bot.edit_message_text("🔄 جاري تجاوز الحماية عبر Cobalt Bridge...", chat_id, msg_id)
        
        # إرسال الطلب للجسر
        response = requests.post(api_url, json=payload, headers=headers)
        result = response.json()
        
        if result.get("status") in ["stream", "picker", "redirect"]:
            direct_link = result.get("url")
            
            bot.edit_message_text("📥 جاري سحب الملف إلى السيرفر...", chat_id, msg_id)
            
            # تحميل الملف من الرابط المباشر
            file_response = requests.get(direct_link, stream=True)
            file_name = f"iShop_{chat_id}.mp4" if quality != 'audio' else f"iShop_{chat_id}.mp3"
            
            with open(file_name, "wb") as f:
                for chunk in file_response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            return file_name, result.get("text", "Video")
        else:
            bot.edit_message_text(f"❌ Cobalt Error: {result.get('text', 'Unknown Error')}", chat_id, msg_id)
            return None, None

    except Exception as e:
        bot.edit_message_text(f"❌ خطأ في الجسر: {str(e)[:100]}", chat_id, msg_id)
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
    bot.reply_to(message, "أهلاً بك في iShop! 👋\nتم تفعيل التحميل عبر Cobalt Bridge بنجاح.")

@bot.message_handler(func=lambda m: m.text.startswith('http'))
def get_link(m):
    user_id = m.from_user.id
    if not check_subscription(user_id):
        bot.reply_to(m, f"⚠️ اشترك في القناة أولاً: {CHANNEL_USERNAME}")
        return

    user_urls[m.chat.id] = m.text
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("تحميل فيديو ✅", callback_data="q|Best"),
               types.InlineKeyboardButton("صوت (MP3) 🎵", callback_data="q|audio"))
    
    bot.reply_to(m, "🎬 تم العثور على الرابط، اختر الصيغة:", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith('q|'))
def process(c):
    user_id = c.message.chat.id
    url = user_urls.get(user_id)
    qual = c.data.split('|')[1]
    
    bot.delete_message(user_id, c.message.message_id)
    msg = bot.send_message(user_id, "⏳ جاري البدء عبر الجسر...")
    
    path, title = download_content(url, qual, user_id, msg.message_id)
    
    if path and os.path.exists(path):
        try:
            bot.edit_message_text("📤 جاري الرفع إلى تيليجرام...", user_id, msg.message_id)
            with open(path, 'rb') as f:
                if qual == 'audio': bot.send_audio(user_id, f)
                else: bot.send_video(user_id, f, caption="تم التحميل بواسطة iShop")
            bot.delete_message(user_id, msg.message_id)
            os.remove(path)
        except Exception as e:
            bot.send_message(user_id, f"فشل الرفع: {e}")
            if os.path.exists(path): os.remove(path)

bot.infinity_polling()
