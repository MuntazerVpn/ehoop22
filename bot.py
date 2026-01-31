import telebot
from telebot import types
import requests
import os

BOT_TOKEN = "8516502699:AAG-yW_GxMjBYtmnD7WhRDnPcONQ1a_qguc"
bot = telebot.TeleBot(BOT_TOKEN)

user_links = {}

# =========================
# 🧠 الجسور
# =========================
COBALT_BRIDGES = [
    "https://api.cobalt.tools/api/json",
    "https://cobalt-api.vercel.app/api/json"
]

HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0"
}

# =========================
# 🔁 نظام الجسور
# =========================
def try_bridges(url, audio, chat_id, msg_id):
    payload = {
        "url": url,
        "vCodec": "h264",
        "vQuality": "720",
        "isAudioOnly": audio,
        "aFormat": "mp3",
        "filenameStyle": "pretty"
    }

    for bridge in COBALT_BRIDGES:
        try:
            bot.edit_message_text(f"🔄 تجربة الجسر:\n{bridge}", chat_id, msg_id)
            r = requests.post(bridge, json=payload, headers=HEADERS, timeout=45)
            data = r.json()

            if "url" in data:
                return data["url"]

        except:
            continue

    return None

# =========================
# 📥 تحميل
# =========================
def download(url, audio, chat_id, msg_id):
    direct = try_bridges(url, audio, chat_id, msg_id)

    if not direct:
        bot.edit_message_text("❌ جميع الجسور فشلت", chat_id, msg_id)
        return None

    ext = "mp3" if audio else "mp4"
    file = f"iShop_{chat_id}.{ext}"

    bot.edit_message_text("📥 تحميل الملف...", chat_id, msg_id)

    with requests.get(direct, stream=True) as r:
        with open(file, "wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                f.write(chunk)

    return file

# =========================
# 🤖 أوامر
# =========================
@bot.message_handler(commands=["start"])
def start(m):
    bot.reply_to(m, "👋 أرسل الرابط وسيتم التحميل تلقائيًا مع جسور احتياطية 🔁")

@bot.message_handler(func=lambda m: m.text.startswith("http"))
def link(m):
    user_links[m.chat.id] = m.text

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("🎬 فيديو", callback_data="v"),
        types.InlineKeyboardButton("🎵 MP3", callback_data="a")
    )

    bot.reply_to(m, "اختر الصيغة 👇", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data in ["v", "a"])
def process(c):
    chat_id = c.message.chat.id
    url = user_links.get(chat_id)

    bot.delete_message(chat_id, c.message.message_id)
    msg = bot.send_message(chat_id, "⏳ جاري المعالجة...")

    path = download(url, c.data == "a", chat_id, msg.message_id)

    if path and os.path.exists(path):
        bot.edit_message_text("📤 رفع إلى تيليجرام...", chat_id, msg.message_id)

        with open(path, "rb") as f:
            if c.data == "a":
                bot.send_audio(chat_id, f)
            else:
                bot.send_video(chat_id, f)

        bot.delete_message(chat_id, msg.message_id)
        os.remove(path)

# =========================
# ▶️ تشغيل
# =========================
print("Bot with backup bridges running...")
bot.infinity_polling()
