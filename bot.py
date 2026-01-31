import os
import re
import json
import time
import threading
import subprocess
from datetime import datetime
from urllib.parse import urlparse

import telebot
from telebot import types


# =========================
# CONFIG (Educational use)
# =========================
BOT_TOKEN = "8423770288:AAGPjI_9TZQXHUGj9bPn7yvORSwQQDHwGJA"
ADMIN_ID = 6964811817

if not BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN is missing. Set env BOT_TOKEN first.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

USERS_FILE = "users.json"
COOKIES_FILE = "cookies.txt"
EDIT_THROTTLE_SEC = 1.2  # منع سبام تعديل الرسائل


# =========================
# State
# =========================
user_links = {}          # chat_id -> last url
chat_locks = {}          # chat_id -> Lock
active_downloads = {}    # chat_id -> {"proc": Popen, "cancel": Event, "dl_id": str, "msg_id": int}


def get_lock(chat_id: int) -> threading.Lock:
    if chat_id not in chat_locks:
        chat_locks[chat_id] = threading.Lock()
    return chat_locks[chat_id]


def load_users() -> dict:
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def save_users(data: dict) -> None:
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except:
        pass


def ensure_user(m):
    users = load_users()
    uid = str(m.from_user.id)
    if uid not in users:
        users[uid] = {
            "first_name": m.from_user.first_name or "",
            "username": (m.from_user.username or ""),
            "added_at": datetime.utcnow().isoformat() + "Z",
        }
        save_users(users)

        # إشعار للآدمن
        if ADMIN_ID:
            total = len(users)
            uname = f"@{m.from_user.username}" if m.from_user.username else "بدون"
            name = (m.from_user.first_name or "بدون اسم")
            bot.send_message(
                ADMIN_ID,
                "👤 مستخدم جديد دخل للبوت\n"
                f"• الاسم: {name}\n"
                f"• المستخدم: {uname}\n"
                f"• ID: <code>{m.from_user.id}</code>\n"
                f"• عدد المستخدمين: <b>{total}</b>"
            )


def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except:
        return ""


def normalize_url(url: str) -> str:
    """
    تحسين دعم Shorts/Reels بشكل أفضل:
    - YouTube Shorts: تحويل /shorts/ID إلى watch?v=ID
    """
    u = url.strip()

    # YouTube shorts
    m = re.search(r"(https?://)?(www\.)?youtube\.com/shorts/([A-Za-z0-9_-]{6,})", u)
    if m:
        vid = m.group(3)
        return f"https://www.youtube.com/watch?v={vid}"

    # youtu.be short link stays okay
    return u


def has_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return True
    except:
        return False


def common_ytdlp_args(domain: str):
    args = [
        "--no-playlist",
        "--sleep-requests", "1",
        "--sleep-interval", "1",
        "--max-sleep-interval", "3",
        "--no-color",
        "--newline",
    ]

    # Instagram: headers + cookies إن وجدت
    if "instagram.com" in domain:
        args += [
            "--user-agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "--add-header", "Referer:https://www.instagram.com/",
            "--add-header", "Origin:https://www.instagram.com",
            "--add-header", "Accept-Language:en-US,en;q=0.9,ar;q=0.8",
        ]
        if os.path.exists(COOKIES_FILE):
            args += ["--cookies", COOKIES_FILE]

    if has_ffmpeg():
        args += ["--merge-output-format", "mp4"]

    return args


def safe_filename(name: str, max_len: int = 80) -> str:
    name = re.sub(r'[\\/:*?"<>|\n\r\t]', "_", name).strip()
    name = re.sub(r"\s+", " ", name)
    if not name:
        name = "download"
    return name[:max_len]


def fmt_upload_date(upload_date: str) -> str:
    try:
        dt = datetime.strptime(upload_date, "%Y%m%d")
        return dt.strftime("%Y-%m-%d")
    except:
        return upload_date or "غير معروف"


def seconds_to_hms(sec: int) -> str:
    try:
        sec = int(sec)
        h = sec // 3600
        m = (sec % 3600) // 60
        s = sec % 60
        if h:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"
    except:
        return "غير معروف"


def human_size(n: int | None) -> str:
    if not n:
        return "غير معروف"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(n)
    i = 0
    while size >= 1024 and i < len(units) - 1:
        size /= 1024
        i += 1
    return f"{size:.2f} {units[i]}"


def fetch_info(url: str, fmt: str, domain: str) -> dict | None:
    try:
        cmd = ["yt-dlp"] + common_ytdlp_args(domain) + ["-f", fmt, "-J", url]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)

        if p.returncode != 0 or not p.stdout.strip():
            return None

        info = json.loads(p.stdout)

        title = info.get("title") or "بدون عنوان"
        channel = info.get("channel") or info.get("uploader") or info.get("uploader_id") or "غير معروف"
        upload_date = fmt_upload_date(info.get("upload_date") or "")
        duration = seconds_to_hms(info.get("duration") or 0)

        # تقدير الحجم (قد لا يكون متاحًا دائمًا)
        size_bytes = None
        if isinstance(info.get("requested_formats"), list) and info["requested_formats"]:
            sizes = []
            for rf in info["requested_formats"]:
                fb = rf.get("filesize") or rf.get("filesize_approx")
                if fb:
                    sizes.append(int(fb))
            if sizes:
                size_bytes = sum(sizes)
        else:
            size_bytes = info.get("filesize") or info.get("filesize_approx")

        return {
            "title": title,
            "channel": channel,
            "upload_date": upload_date,
            "duration": duration,
            "size_bytes": int(size_bytes) if size_bytes else None,
        }
    except:
        return None


def find_file(prefix: str):
    files = [f for f in os.listdir(".") if f.startswith(prefix)]
    if not files:
        return None
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    return files[0]


def build_format(domain: str, mode: str) -> str:
    ff = has_ffmpeg()

    # Instagram: فيديو فقط (مناسب للريلز)
    if mode == "ig_video":
        if ff:
            return "bestvideo[vcodec^=avc1]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        return "best[ext=mp4][vcodec^=avc1]/best[ext=mp4]/best"

    # Audio only
    if mode.endswith("_audio"):
        return "bestaudio/best"

    # Fixed resolutions
    if mode.endswith("_720"):
        return "bestvideo[height<=720][vcodec^=avc1]+bestaudio[ext=m4a]/best[height<=720]/best"
    if mode.endswith("_480"):
        return "bestvideo[height<=480][vcodec^=avc1]+bestaudio[ext=m4a]/best[height<=480]/best"
    if mode.endswith("_360"):
        return "bestvideo[height<=360][vcodec^=avc1]+bestaudio[ext=m4a]/best[height<=360]/best"

    # fallback
    return "best"


def cancel_keyboard(dl_id: str):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🛑 إلغاء التحميل", callback_data=f"cancel:{dl_id}"))
    return kb


def stop_process(proc: subprocess.Popen):
    try:
        proc.terminate()
    except:
        pass
    # kill if still alive
    for _ in range(10):
        if proc.poll() is not None:
            return
        time.sleep(0.2)
    try:
        proc.kill()
    except:
        pass


def ytdlp_download_with_progress(url, mode, chat_id, msg_id, dl_id):
    url = normalize_url(url)
    domain = get_domain(url)
    out_prefix = f"dl_{chat_id}_{int(time.time())}"
    out_tmpl = f"{out_prefix}.%(ext)s"

    fmt = build_format(domain, mode)

    # جلب معلومات قبل التحميل
    info = fetch_info(url, fmt, domain) or {}
    title = info.get("title", "بدون عنوان")
    channel = info.get("channel", "غير معروف")
    upload_date = info.get("upload_date", "غير معروف")
    duration = info.get("duration", "غير معروف")
    size_str = human_size(info.get("size_bytes"))

    pre = (
        "📌 <b>معلومات قبل التحميل</b>\n"
        f"🎬 <b>العنوان:</b> {title}\n"
        f"👤 <b>القناة/الناشر:</b> {channel}\n"
        f"📅 <b>تاريخ النشر:</b> {upload_date}\n"
        f"⏱️ <b>المدة:</b> {duration}\n"
        f"📦 <b>الحجم التقريبي:</b> {size_str}\n\n"
        "⬇️ <b>التحميل:</b> 0%"
    )

    try:
        bot.edit_message_text(pre, chat_id, msg_id, reply_markup=cancel_keyboard(dl_id))
    except:
        pass

    cmd = ["yt-dlp"] + common_ytdlp_args(domain) + [
        "-f", fmt,
        "-o", out_tmpl,
        url
    ]

    percent_re = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")
    eta_re = re.compile(r"ETA\s+(\d+:\d+|\d+)")
    speed_re = re.compile(r"at\s+([0-9.]+\w+/s)")

    last_update_t = 0.0
    last_percent_int = -1

    cancel_event = active_downloads[chat_id]["cancel"]

    try:
        # start process
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        active_downloads[chat_id]["proc"] = proc

        for line in proc.stdout:
            if cancel_event.is_set():
                stop_process(proc)
                try:
                    bot.edit_message_text("🛑 تم إلغاء التحميل.", chat_id, msg_id)
                except:
                    pass
                return None, None, None

            m = percent_re.search(line)
            if not m:
                continue

            pct = float(m.group(1))
            pct_int = int(pct)

            now = time.time()
            if pct_int == last_percent_int and (now - last_update_t) < EDIT_THROTTLE_SEC:
                continue
            if (now - last_update_t) < EDIT_THROTTLE_SEC:
                continue

            last_percent_int = pct_int
            last_update_t = now

            eta_m = eta_re.search(line)
            speed_m = speed_re.search(line)
            eta = eta_m.group(1) if eta_m else ""
            spd = speed_m.group(1) if speed_m else ""

            extra = []
            if spd:
                extra.append(f"🚀 {spd}")
            if eta:
                extra.append(f"⏳ ETA {eta}")

            progress_text = (
                "📌 <b>معلومات قبل التحميل</b>\n"
                f"🎬 <b>العنوان:</b> {title}\n"
                f"👤 <b>القناة/الناشر:</b> {channel}\n"
                f"📅 <b>تاريخ النشر:</b> {upload_date}\n"
                f"⏱️ <b>المدة:</b> {duration}\n"
                f"📦 <b>الحجم التقريبي:</b> {size_str}\n\n"
                f"⬇️ <b>التحميل:</b> {pct_int}%"
                + (f"\n{' | '.join(extra)}" if extra else "")
            )

            try:
                bot.edit_message_text(progress_text, chat_id, msg_id, reply_markup=cancel_keyboard(dl_id))
            except:
                pass

        ret = proc.wait()
        if cancel_event.is_set():
            try:
                bot.edit_message_text("🛑 تم إلغاء التحميل.", chat_id, msg_id)
            except:
                pass
            return None, None, None

        if ret != 0:
            try:
                bot.edit_message_text("❌ فشل التحميل (yt-dlp error).", chat_id, msg_id)
            except:
                pass
            return None, None, None

        path = find_file(out_prefix)
        return path, title, channel

    except Exception as e:
        try:
            bot.edit_message_text(f"❌ فشل التحميل: {e}", chat_id, msg_id)
        except:
            pass
        return None, None, None


def send_result(chat_id: int, msg_id: int, path: str, mode: str, title: str, channel: str):
    # rename to title
    base, ext = os.path.splitext(path)
    nice = safe_filename(title or "download")
    new_path = f"{nice}{ext}"
    try:
        if os.path.exists(new_path):
            os.remove(new_path)
        os.rename(path, new_path)
        path = new_path
    except:
        pass

    try:
        bot.edit_message_text("📤 رفع إلى تيليجرام...", chat_id, msg_id)
    except:
        pass

    with open(path, "rb") as f:
        if mode.endswith("_audio"):
            bot.send_audio(
                chat_id,
                f,
                title=title or "Audio",
                performer=channel or "",
                caption=f"🎵 {title}" if title else None
            )
        else:
            bot.send_video(
                chat_id,
                f,
                caption=f"🎬 {title}" if title else None
            )

    try:
        bot.delete_message(chat_id, msg_id)
    except:
        pass

    try:
        os.remove(path)
    except:
        pass


def handle_download(chat_id, url, mode, status_msg_id):
    lock = get_lock(chat_id)
    if not lock.acquire(blocking=False):
        try:
            bot.edit_message_text("⚠️ انتظر، هناك تحميل شغال بالفعل...", chat_id, status_msg_id)
        except:
            pass
        return

    try:
        # create download session id
        dl_id = f"{chat_id}:{int(time.time())}"
        active_downloads[chat_id] = {
            "proc": None,
            "cancel": threading.Event(),
            "dl_id": dl_id,
            "msg_id": status_msg_id
        }

        path, title, channel = ytdlp_download_with_progress(url, mode, chat_id, status_msg_id, dl_id)

        # if canceled or failed
        if not path or not os.path.exists(path):
            return

        send_result(chat_id, status_msg_id, path, mode, title, channel)

    finally:
        # cleanup
        try:
            active_downloads.pop(chat_id, None)
        except:
            pass
        lock.release()


# =========================
# BOT Handlers
# =========================
@bot.message_handler(commands=["start"])
def start(m):
    ensure_user(m)
    bot.reply_to(
        m,
        "👋 <b>أرسل الرابط</b>\n\n"
        "🔹 يوتيوب/تيك توك: 720 / 480 / 360 / صوت\n"
        "🔹 إنستغرام (Reels): فيديو فقط\n\n"
        "✅ يظهر اسم المقطع ومعلومات قبل التحميل + نسبة التحميل %\n"
        "🛑 يوجد زر إلغاء أثناء التحميل\n\n"
        "📚 <i>هذا البوت لأغراض تعليمية.</i>"
    )


@bot.message_handler(func=lambda m: m.text and m.text.strip().startswith("http"))
def link(m):
    ensure_user(m)
    url = normalize_url(m.text.strip())
    domain = get_domain(url)
    user_links[m.chat.id] = url

    kb = types.InlineKeyboardMarkup(row_width=1)

    if "instagram.com" in domain:
        kb.add(types.InlineKeyboardButton("📸 تحميل فيديو (Reels/Instagram)", callback_data="ig_video"))
    elif "youtube.com" in domain or "youtu.be" in domain:
        kb.add(
            types.InlineKeyboardButton("🎬 فيديو 720p", callback_data="yt_720"),
            types.InlineKeyboardButton("🎬 فيديو 480p", callback_data="yt_480"),
            types.InlineKeyboardButton("🎬 فيديو 360p", callback_data="yt_360"),
            types.InlineKeyboardButton("🎵 صوت فقط", callback_data="yt_audio"),
        )
    elif "tiktok.com" in domain:
        kb.add(
            types.InlineKeyboardButton("🎬 فيديو 720p", callback_data="tk_720"),
            types.InlineKeyboardButton("🎬 فيديو 480p", callback_data="tk_480"),
            types.InlineKeyboardButton("🎬 فيديو 360p", callback_data="tk_360"),
            types.InlineKeyboardButton("🎵 صوت فقط", callback_data="tk_audio"),
        )
    else:
        kb.add(
            types.InlineKeyboardButton("🎬 فيديو 720p", callback_data="yt_720"),
            types.InlineKeyboardButton("🎬 فيديو 480p", callback_data="yt_480"),
            types.InlineKeyboardButton("🎬 فيديو 360p", callback_data="yt_360"),
            types.InlineKeyboardButton("🎵 صوت فقط", callback_data="yt_audio"),
        )

    bot.reply_to(m, "اختر الجودة 👇", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("cancel:"))
def cancel_download(c):
    chat_id = c.message.chat.id
    dl = active_downloads.get(chat_id)

    # لو ماكو تحميل فعّال
    if not dl:
        try:
            bot.answer_callback_query(c.id, "لا يوجد تحميل شغال الآن.")
        except:
            pass
        return

    # تأكد أنه نفس الجلسة
    dl_id = c.data.split(":", 1)[1]
    if dl.get("dl_id") != dl_id:
        try:
            bot.answer_callback_query(c.id, "هذا زر قديم.")
        except:
            pass
        return

    dl["cancel"].set()
    proc = dl.get("proc")
    if proc and proc.poll() is None:
        stop_process(proc)

    try:
        bot.answer_callback_query(c.id, "تم الإلغاء.")
    except:
        pass
    try:
        bot.edit_message_text("🛑 تم إلغاء التحميل.", chat_id, dl.get("msg_id", c.message.message_id))
    except:
        pass


@bot.callback_query_handler(func=lambda c: c.data in [
    "ig_video",
    "yt_720", "yt_480", "yt_360", "yt_audio",
    "tk_720", "tk_480", "tk_360", "tk_audio",
])
def process_choice(c):
    chat_id = c.message.chat.id
    url = user_links.get(chat_id)

    # امسح لوحة الاختيارات
    try:
        bot.delete_message(chat_id, c.message.message_id)
    except:
        pass

    msg = bot.send_message(chat_id, "⏳ بدء التحميل...")

    if not url:
        bot.edit_message_text("❌ أرسل الرابط مرة ثانية.", chat_id, msg.message_id)
        return

    # تشغيل التحميل في Thread
    t = threading.Thread(
        target=handle_download,
        args=(chat_id, url, c.data, msg.message_id),
        daemon=True
    )
    t.start()


def run_bot():
    while True:
        try:
            bot.remove_webhook()
            bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            print("Polling crashed:", e)
            time.sleep(5)


print("Bot running 🔥 (Educational use)")
run_bot()
