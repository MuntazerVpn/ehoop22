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
    raise SystemExit("❌ BOT_TOKEN missing. Set BOT_TOKEN env var first.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

USERS_FILE = "users.json"
COOKIES_FILE = "cookies.txt"
EDIT_THROTTLE_SEC = 1.2  # منع سبام تعديل الرسائل

user_links = {}          # chat_id -> last url
chat_locks = {}          # chat_id -> Lock
active_downloads = {}    # chat_id -> {"proc": Popen, "cancel": Event, "dl_id": str, "msg_id": int}


# =========================
# Helpers
# =========================
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

        if ADMIN_ID:
            total = len(users)
            uname = f"@{m.from_user.username}" if m.from_user.username else "بدون"
            name = (m.from_user.first_name or "بدون اسم")
            bot.send_message(
                ADMIN_ID,
                "👤 <b>مستخدم جديد دخل للبوت</b>\n"
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
    u = (url or "").strip()
    # YouTube shorts -> watch
    m = re.search(r"(https?://)?(www\.)?youtube\.com/shorts/([A-Za-z0-9_-]{6,})", u)
    if m:
        vid = m.group(3)
        return f"https://www.youtube.com/watch?v={vid}"
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
        "--force-overwrites",
    ]

    # Instagram headers + cookies
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

    return args


def find_file(prefix: str):
    files = [f for f in os.listdir(".") if f.startswith(prefix)]
    if not files:
        return None
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    return files[0]


def safe_filename(name: str, max_len: int = 80) -> str:
    name = re.sub(r'[\\/:*?"<>|\n\r\t]', "_", (name or "")).strip()
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
    """
    معلومات قبل التحميل: عنوان/قناة/تاريخ/مدة/حجم تقريبي
    """
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


def cancel_keyboard(dl_id: str):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🛑 إلغاء التحميل", callback_data=f"cancel:{dl_id}"))
    return kb


def stop_process(proc: subprocess.Popen):
    try:
        proc.terminate()
    except:
        pass
    for _ in range(10):
        if proc.poll() is not None:
            return
        time.sleep(0.2)
    try:
        proc.kill()
    except:
        pass


# =========================
# Format selection: ONLY 720 / 480 / audio
# إذا غير متوفرين => ينزل أي جودة تلقائيًا
# =========================
def build_format(domain: str, mode: str) -> str:
    # Instagram: فيديو فقط
    if mode == "ig_video":
        return "best[ext=mp4][vcodec!=none][acodec!=none]/best"

    # Audio
    if mode == "v_audio":
        return "bestaudio[ext=m4a]/bestaudio/best"

    # Video 720
    if mode == "v_720":
        return (
            "best[height<=720][ext=mp4][vcodec!=none][acodec!=none]/"
            "best[ext=mp4][vcodec!=none][acodec!=none]/"
            "best"
        )

    # Video 480
    if mode == "v_480":
        return (
            "best[height<=480][ext=mp4][vcodec!=none][acodec!=none]/"
            "best[ext=mp4][vcodec!=none][acodec!=none]/"
            "best"
        )

    return "best"


# =========================
# Download with progress + info + cancel
# =========================
def ytdlp_download_with_progress(url, mode, chat_id, msg_id, dl_id):
    url = normalize_url(url)
    domain = get_domain(url)

    out_prefix = f"dl_{chat_id}_{int(time.time())}"
    out_tmpl = f"{out_prefix}.%(ext)s"

    fmt = build_format(domain, mode)

    # معلومات قبل التحميل ✅
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

    extra_args = []
    if mode != "v_audio":
        if has_ffmpeg():
            extra_args += ["--merge-output-format", "mp4", "--remux-video", "mp4"]
        else:
            extra_args += ["--format-sort", "ext:mp4"]
    else:
        if has_ffmpeg():
            extra_args += ["-x", "--audio-format", "m4a", "--audio-quality", "0"]

    cmd = ["yt-dlp"] + common_ytdlp_args(domain) + ["-f", fmt] + extra_args + ["-o", out_tmpl, url]

    percent_re = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")
    eta_re = re.compile(r"ETA\s+(\d+:\d+|\d+)")
    speed_re = re.compile(r"at\s+([0-9.]+\w+/s)")

    last_update_t = 0.0
    cancel_event = active_downloads[chat_id]["cancel"]

    try:
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

            pct_int = int(float(m.group(1)))
            now = time.time()
            if (now - last_update_t) < EDIT_THROTTLE_SEC:
                continue
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
        if mode == "v_audio":
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
                caption=f"🎬 {title}" if title else None,
                supports_streaming=True
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
        dl_id = f"{chat_id}:{int(time.time())}"
        active_downloads[chat_id] = {
            "proc": None,
            "cancel": threading.Event(),
            "dl_id": dl_id,
            "msg_id": status_msg_id
        }

        path, title, channel = ytdlp_download_with_progress(url, mode, chat_id, status_msg_id, dl_id)
        if not path or not os.path.exists(path):
            return

        send_result(chat_id, status_msg_id, path, mode, title, channel)

    finally:
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
        "🔹 يوتيوب/تيك توك: <b>720p</b> أو <b>480p</b> أو <b>صوت</b>\n"
        "🔹 إنستغرام: فيديو فقط\n\n"
        "✅ يعرض معلومات قبل التحميل + نسبة التحميل %\n"
        "🛑 زر إلغاء أثناء التحميل\n\n"
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
        kb.add(types.InlineKeyboardButton("📸 تحميل فيديو (إنستغرام)", callback_data="ig_video"))
    else:
        kb.add(
            types.InlineKeyboardButton("🎬 فيديو 720p", callback_data="v_720"),
            types.InlineKeyboardButton("🎬 فيديو 480p", callback_data="v_480"),
            types.InlineKeyboardButton("🎵 صوت فقط", callback_data="v_audio"),
        )

    bot.reply_to(m, "اختر الخيار 👇", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("cancel:"))
def cancel_download(c):
    chat_id = c.message.chat.id
    dl = active_downloads.get(chat_id)

    if not dl:
        try:
            bot.answer_callback_query(c.id, "لا يوجد تحميل شغال الآن.")
        except:
            pass
        return

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


@bot.callback_query_handler(func=lambda c: c.data in ["ig_video", "v_720", "v_480", "v_audio"])
def process_choice(c):
    chat_id = c.message.chat.id
    url = user_links.get(chat_id)

    try:
        bot.delete_message(chat_id, c.message.message_id)
    except:
        pass

    msg = bot.send_message(chat_id, "⏳ بدء التحميل...")

    if not url:
        bot.edit_message_text("❌ أرسل الرابط مرة ثانية.", chat_id, msg.message_id)
        return

    mode = c.data  # ig_video / v_720 / v_480 / v_audio
    t = threading.Thread(target=handle_download, args=(chat_id, url, mode, msg.message_id), daemon=True)
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
