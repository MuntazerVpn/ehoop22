import os
import re
import sys
import json
import time
import threading
import subprocess
from datetime import datetime
from urllib.parse import urlparse

import telebot
from telebot import types

# =========================
# CONFIG
# =========================
BOT_TOKEN = "8423770288:AAGPjI_9TZQXHUGj9bPn7yvORSwQQDHwGJA"
ADMIN_ID = 6964811817
if not BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN missing. Set it as env var BOT_TOKEN")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

USERS_FILE = "users.json"
SETTINGS_FILE = "settings.json"
USAGE_FILE = "usage.json"
STATS_FILE = "stats.json"
COOKIES_FILE = "cookies.txt"

IG_COOKIES = os.getenv("IG_COOKIES", "").strip()
if IG_COOKIES:
    try:
        with open(COOKIES_FILE, "w", encoding="utf-8") as f:
            f.write(IG_COOKIES)
    except:
        pass

EDIT_THROTTLE_SEC = 1.2
IDLE_TIMEOUT_SEC = 180  # عام لكل المواقع
MAX_ATTEMPTS = 2        # إعادة محاولة مرة وحدة
BACKOFF_SEC = [0, 15]   # تأخير قبل المحاولة الثانية

user_links = {}
chat_locks = {}
active_downloads = {}  # chat_id -> {"proc": Popen, "cancel": Event, "dl_id": str, "msg_id": int}

# =========================
# DEFAULT SETTINGS
# =========================
DEFAULT_SETTINGS = {
    "bot_enabled": True,
    "bot_public_username": "@aass554411",
    "welcome_message": (
        "👋 <b>هلا بيك!</b>\n"
        "أنا بوت التحميل مالك: <b>منتظر</b>\n\n"
        "✅ أرسل الرابط مباشرة\n"
        "🔹 يوتيوب/تيك توك: <b>مقطع</b> أو <b>ملف صوتي</b> أو <b>بصمة</b>\n"
        "🔹 إنستغرام: فيديو فقط\n\n"
        "🛑 تقدر تلغي التحميل أثناء التشغيل\n"
        "⚠️ الحد اليومي لكل مستخدم: <b>20 رابط</b>\n"
        "—\n"
        "🔗 بوتي: @aass554411"
    ),
    "daily_limit": 20,
    "forced_channels": [],
    "buttons": {
        "start_btn": "✅ بدء",
        "admin_btn": "⚙️ ادمن",
        "clip": "🎬 مقطع فيديو",
        "audio_file": "🎵 ملف صوتي",
        "voice_note": "🎙️ بصمة صوتية",
        "ig_video": "📸 تحميل فيديو (إنستغرام)",
        "cancel": "🛑 إلغاء التحميل",
    },
}

# =========================
# JSON HELPERS
# =========================
def _load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def _save_json(path: str, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except:
        pass

settings_lock = threading.Lock()
stats_lock = threading.Lock()

def load_settings():
    s = _load_json(SETTINGS_FILE, {})
    merged = json.loads(json.dumps(DEFAULT_SETTINGS))
    for k, v in s.items():
        if k == "buttons" and isinstance(v, dict):
            merged["buttons"].update(v)
        else:
            merged[k] = v
    return merged

def save_settings(s):
    _save_json(SETTINGS_FILE, s)

def load_users() -> dict:
    return _load_json(USERS_FILE, {})

def save_users(data: dict) -> None:
    _save_json(USERS_FILE, data)

def load_usage() -> dict:
    return _load_json(USAGE_FILE, {})

def save_usage(d: dict):
    _save_json(USAGE_FILE, d)

def log_stat(event: dict):
    with stats_lock:
        stats = _load_json(STATS_FILE, [])
        stats.append(event)
        stats = stats[-5000:]
        _save_json(STATS_FILE, stats)

# =========================
# BASIC HELPERS
# =========================
def get_lock(chat_id: int) -> threading.Lock:
    if chat_id not in chat_locks:
        chat_locks[chat_id] = threading.Lock()
    return chat_locks[chat_id]

def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except:
        return ""

def normalize_url(url: str) -> str:
    u = (url or "").strip()
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

def safe_filename(name: str, max_len: int = 80) -> str:
    name = re.sub(r'[\\/:*?"<>|\n\r\t]', "_", (name or "")).strip()
    name = re.sub(r"\s+", " ", name)
    return (name[:max_len] if name else "download")

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

def human_size(n):
    if not n:
        return "غير معروف"
    try:
        n = int(n)
    except:
        return "غير معروف"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(n)
    i = 0
    while size >= 1024 and i < len(units) - 1:
        size /= 1024
        i += 1
    return f"{size:.2f} {units[i]}"

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

def is_admin(user_id: int) -> bool:
    return int(user_id) == int(ADMIN_ID)

# =========================
# KEYBOARDS
# =========================
def start_keyboard(user_id: int = None):
    s = load_settings()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(s["buttons"]["start_btn"])
    if user_id is not None and is_admin(user_id):
        kb.row(s["buttons"]["admin_btn"])
    return kb

def cancel_keyboard(dl_id: str):
    s = load_settings()
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(s["buttons"]["cancel"], callback_data=f"cancel:{dl_id}"))
    return kb

def admin_panel_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✉️ الترحيب", callback_data="adm:welcome"),
        types.InlineKeyboardButton("🚫 حظر/فك", callback_data="adm:ban"),
    )
    kb.add(
        types.InlineKeyboardButton("🧷 الأزرار", callback_data="adm:buttons"),
        types.InlineKeyboardButton("📢 إذاعة", callback_data="adm:broadcast"),
    )
    kb.add(
        types.InlineKeyboardButton("✅ اشتراك إجباري", callback_data="adm:force"),
        types.InlineKeyboardButton("⏸️ تشغيل/إيقاف", callback_data="adm:toggle"),
    )
    kb.add(
        types.InlineKeyboardButton("🔁 إعادة تشغيل", callback_data="adm:restart"),
        types.InlineKeyboardButton("📊 تقرير الآن", callback_data="adm:report"),
    )
    return kb

def force_join_kb(channels: list):
    kb = types.InlineKeyboardMarkup(row_width=1)
    for ch in channels[:8]:
        ch_disp = ch if ch.startswith("@") else f"@{ch}"
        kb.add(types.InlineKeyboardButton(f"📌 {ch_disp}", url=f"https://t.me/{ch_disp.lstrip('@')}"))
    kb.add(types.InlineKeyboardButton("✅ تحقّق", callback_data="force:check"))
    return kb

# =========================
# USERS + BAN
# =========================
def ensure_user(m):
    users = load_users()
    uid = str(m.from_user.id)
    if uid not in users:
        users[uid] = {
            "first_name": m.from_user.first_name or "",
            "username": (m.from_user.username or ""),
            "added_at": datetime.utcnow().isoformat() + "Z",
            "banned": False,
        }
        save_users(users)

        if ADMIN_ID:
            total = len(users)
            uname = f"@{m.from_user.username}" if m.from_user.username else "بدون"
            name = (m.from_user.first_name or "بدون اسم")
            bot.send_message(
                ADMIN_ID,
                "👤 <b>مستخدم جديد</b>\n"
                f"• الاسم: {name}\n"
                f"• المستخدم: {uname}\n"
                f"• ID: <code>{m.from_user.id}</code>\n"
                f"• عدد المستخدمين: <b>{total}</b>",
                reply_markup=start_keyboard(ADMIN_ID)
            )

def is_banned(user_id: int) -> bool:
    users = load_users()
    u = users.get(str(user_id))
    return bool(u and u.get("banned"))

def set_ban(user_id: int, banned: bool):
    users = load_users()
    uid = str(user_id)
    if uid not in users:
        users[uid] = {"first_name": "", "username": "", "added_at": datetime.utcnow().isoformat() + "Z"}
    users[uid]["banned"] = bool(banned)
    save_users(users)

# =========================
# BOT ENABLE / FORCED JOIN / LIMIT
# =========================
def bot_is_enabled_for(user_id: int) -> bool:
    s = load_settings()
    if s.get("bot_enabled", True):
        return True
    return is_admin(user_id)

def check_forced_join(user_id: int) -> bool:
    s = load_settings()
    channels = s.get("forced_channels") or []
    if not channels:
        return True

    for ch in channels:
        try:
            mem = bot.get_chat_member(ch, user_id)
            if mem.status in ("left", "kicked"):
                return False
        except:
            return False
    return True

def daily_limit_ok(user_id: int) -> (bool, int, int):
    s = load_settings()
    limit = int(s.get("daily_limit", 20))
    usage = load_usage()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    key = str(user_id)
    if key not in usage:
        usage[key] = {}
    cnt = int(usage[key].get(today, 0))
    return (cnt < limit, cnt, limit)

def inc_daily(user_id: int):
    usage = load_usage()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    key = str(user_id)
    if key not in usage:
        usage[key] = {}
    usage[key][today] = int(usage[key].get(today, 0)) + 1
    save_usage(usage)

def refuse_plain(chat_id: int, user_id: int):
    s = load_settings()
    bot.send_message(
        chat_id,
        "⚠️ <b>أرسل رابط صحيح</b>\n"
        "مثال: https://youtube.com/...\n\n"
        f"اضغط {s['buttons']['start_btn']} للبدء.",
        reply_markup=start_keyboard(user_id)
    )

# =========================
# yt-dlp ARGS / FORMATS
# =========================
def youtube_client_args(attempt: int):
    if attempt <= 0:
        return ["--extractor-args", "youtube:player_client=android"]
    return ["--extractor-args", "youtube:player_client=web"]

def common_ytdlp_args(domain: str):
    args = [
        "--no-playlist",
        "--no-color",
        "--newline",
        "--force-overwrites",
        "--no-check-certificate",
        "--socket-timeout", "20",
        "--retries", "20",
        "--fragment-retries", "20",
        "--file-access-retries", "20",
        "--retry-sleep", "1",
        "--force-ipv4",
        "--concurrent-fragments", "1",
        "--sleep-interval", "2",
        "--max-sleep-interval", "6",
        "--extractor-retries", "20",
        "--http-chunk-size", "10M",
    ]

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

def build_format(domain: str, mode: str) -> str:
    if mode == "ig_video":
        return (
            "bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
            "best[ext=mp4][vcodec^=avc1]/"
            "best"
        )
    if mode == "v_clip":
        return "best[ext=mp4][vcodec!=none][acodec!=none]/best"
    if mode in ("a_m4a", "a_voice"):
        return "bestaudio/best"
    return "best"

def find_file(prefix: str):
    files = [f for f in os.listdir(".") if f.startswith(prefix)]
    if not files:
        return None
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    return files[0]

# =========================
# FETCH INFO
# =========================
def fetch_info(url: str, fmt: str, domain: str):
    try:
        cmd = ["yt-dlp"] + common_ytdlp_args(domain)
        if "youtube.com" in domain or "youtu.be" in domain:
            cmd += youtube_client_args(0)
        cmd += ["-f", fmt, "-J", url]

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

# =========================
# DOWNLOAD WITH PROGRESS + CANCEL + WATCHDOG + RETRY
# =========================
def ytdlp_download_with_progress(url, mode, chat_id, msg_id, dl_id, user_id):
    url = normalize_url(url)
    domain = get_domain(url)

    out_prefix = f"dl_{chat_id}_{int(time.time())}"
    out_tmpl = f"{out_prefix}.%(ext)s"
    fmt = build_format(domain, mode)

    info = fetch_info(url, fmt, domain) or {}
    title = info.get("title", "بدون عنوان")
    channel = info.get("channel", "غير معروف")
    upload_date = info.get("upload_date", "غير معروف")
    duration = info.get("duration", "غير معروف")
    size_str = human_size(info.get("size_bytes"))

    base_pre = (
        "📌 <b>معلومات قبل التحميل</b>\n"
        f"🎬 <b>العنوان:</b> {title}\n"
        f"👤 <b>القناة/الناشر:</b> {channel}\n"
        f"📅 <b>تاريخ النشر:</b> {upload_date}\n"
        f"⏱️ <b>المدة:</b> {duration}\n"
        f"📦 <b>الحجم التقريبي:</b> {size_str}\n\n"
    )

    try:
        bot.edit_message_text(base_pre + "⬇️ <b>التحميل:</b> 0%", chat_id, msg_id, reply_markup=cancel_keyboard(dl_id))
    except:
        pass

    extra_args = []
    if mode in ("a_m4a", "a_voice"):
        if has_ffmpeg():
            if mode == "a_m4a":
                extra_args += ["-x", "--audio-format", "m4a", "--audio-quality", "0"]
            else:
                extra_args += ["-x", "--audio-format", "opus", "--audio-quality", "0"]
    else:
        if has_ffmpeg():
            extra_args += ["--merge-output-format", "mp4", "--remux-video", "mp4"]
            if "instagram.com" in domain:
                extra_args += [
                    "--postprocessor-args",
                    "ffmpeg:-c:v libx264 -pix_fmt yuv420p -c:a aac -b:a 128k -movflags +faststart"
                ]
        else:
            extra_args += ["--format-sort", "ext:mp4"]

    percent_re = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")
    eta_re = re.compile(r"ETA\s+(\d+:\d+|\d+)")
    speed_re = re.compile(r"at\s+([0-9.]+\w+/s)")
    status_re = re.compile(r"(Downloading|Extracting|Requesting|Fetching|webpage|JSON|API|Retry)", re.IGNORECASE)

    cancel_event = active_downloads[chat_id]["cancel"]

    def make_cmd(attempt: int):
        cmd = ["yt-dlp"] + common_ytdlp_args(domain)
        if "youtube.com" in domain or "youtu.be" in domain:
            cmd += youtube_client_args(attempt)
        cmd += ["-f", fmt] + extra_args + ["-o", out_tmpl, url]
        return cmd

    for attempt in range(MAX_ATTEMPTS):
        if cancel_event.is_set():
            return None, None, None, None, "CANCELLED"

        if BACKOFF_SEC[min(attempt, len(BACKOFF_SEC)-1)]:
            time.sleep(BACKOFF_SEC[min(attempt, len(BACKOFF_SEC)-1)])

        if attempt > 0:
            try:
                bot.edit_message_text(
                    base_pre + f"🔁 <b>إعادة محاولة ({attempt+1}/{MAX_ATTEMPTS})...</b>",
                    chat_id, msg_id,
                    reply_markup=cancel_keyboard(dl_id)
                )
            except:
                pass

        cmd = make_cmd(attempt)

        last_update_t = 0.0
        last_output_t = time.time()
        timed_out_flag = {"hit": False}

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

            def watchdog():
                while proc.poll() is None and not cancel_event.is_set():
                    if time.time() - last_output_t > IDLE_TIMEOUT_SEC:
                        timed_out_flag["hit"] = True
                        stop_process(proc)
                        return
                    time.sleep(2)

            threading.Thread(target=watchdog, daemon=True).start()

            for line in proc.stdout:
                last_output_t = time.time()

                if cancel_event.is_set():
                    stop_process(proc)
                    try:
                        bot.edit_message_text("CANCELLED", chat_id, msg_id, reply_markup=start_keyboard(user_id))
                    except:
                        pass
                    log_stat({"ts": time.time(), "type": "cancel", "chat_id": chat_id, "domain": domain})
                    return None, None, None, None, "CANCELLED"

                if status_re.search(line):
                    now = time.time()
                    if (now - last_update_t) >= EDIT_THROTTLE_SEC:
                        last_update_t = now
                        try:
                            bot.edit_message_text(
                                base_pre + "⏳ <b>جارِ التحضير/الاستخراج...</b>",
                                chat_id, msg_id,
                                reply_markup=cancel_keyboard(dl_id)
                            )
                        except:
                            pass

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

                progress_text = base_pre + f"⬇️ <b>التحميل:</b> {pct_int}%" + (f"\n{' | '.join(extra)}" if extra else "")
                try:
                    bot.edit_message_text(progress_text, chat_id, msg_id, reply_markup=cancel_keyboard(dl_id))
                except:
                    pass

            ret = proc.wait()

            if cancel_event.is_set():
                return None, None, None, None, "CANCELLED"

            if timed_out_flag["hit"]:
                if attempt < MAX_ATTEMPTS - 1:
                    continue
                try:
                    bot.edit_message_text(
                        "⛔ <b>Timeout</b>\n"
                        "التحميل علّق/النت بطيء أو الموقع منع الطلب مؤقتاً.\n"
                        "✅ جرّب بعد دقيقة.",
                        chat_id, msg_id,
                        reply_markup=start_keyboard(user_id)
                    )
                except:
                    pass
                log_stat({"ts": time.time(), "type": "fail", "reason": "TIMEOUT", "chat_id": chat_id, "domain": domain})
                return None, None, None, None, "TIMEOUT"

            if ret != 0:
                if attempt < MAX_ATTEMPTS - 1:
                    continue
                try:
                    bot.edit_message_text(
                        "YT_DLP_ERROR\n"
                        "✅ جرّب بعد دقيقة أو جرّب رابط ثاني.",
                        chat_id, msg_id, reply_markup=start_keyboard(user_id)
                    )
                except:
                    pass
                log_stat({"ts": time.time(), "type": "fail", "reason": "YT_DLP_ERROR", "chat_id": chat_id, "domain": domain})
                return None, None, None, None, "YT_DLP_ERROR"

            path = find_file(out_prefix)
            if not path:
                try:
                    bot.edit_message_text("FILE_NOT_FOUND", chat_id, msg_id, reply_markup=start_keyboard(user_id))
                except:
                    pass
                log_stat({"ts": time.time(), "type": "fail", "reason": "FILE_NOT_FOUND", "chat_id": chat_id, "domain": domain})
                return None, None, None, None, "FILE_NOT_FOUND"

            return path, title, channel, duration, None

        except:
            if attempt < MAX_ATTEMPTS - 1:
                continue
            try:
                bot.edit_message_text("RUNTIME_ERROR", chat_id, msg_id, reply_markup=start_keyboard(user_id))
            except:
                pass
            log_stat({"ts": time.time(), "type": "fail", "reason": "RUNTIME_ERROR", "chat_id": chat_id, "domain": domain})
            return None, None, None, None, "RUNTIME_ERROR"

    return None, None, None, None, "DOWNLOAD_FAILED"

def send_result(chat_id: int, msg_id: int, path: str, mode: str, title: str, channel: str, duration: str):
    s = load_settings()
    bot_link = s.get("bot_public_username") or "@aass554411"

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

    caption_tail = f"\n\n🔗 {bot_link}"

    if mode == "a_voice":
        final_path = path
        if has_ffmpeg() and not path.lower().endswith(".ogg"):
            ogg_path = f"{os.path.splitext(path)[0]}.ogg"
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", path, "-vn", "-c:a", "libopus", "-b:a", "64k", ogg_path],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
                )
                if os.path.exists(ogg_path):
                    final_path = ogg_path
            except:
                pass

        try:
            with open(final_path, "rb") as vf:
                bot.send_voice(
                    chat_id,
                    vf,
                    caption=(f"🎙️ {title}\n⏱️ {duration}" if title else f"🎙️\n⏱️ {duration}") + caption_tail
                )
        finally:
            if final_path != path:
                try:
                    os.remove(final_path)
                except:
                    pass
    else:
        with open(path, "rb") as f:
            if mode == "a_m4a":
                bot.send_audio(
                    chat_id,
                    f,
                    title=title or "Audio",
                    performer=channel or "",
                    caption=(f"🎵 {title}\n⏱️ {duration}" if title else f"🎵\n⏱️ {duration}") + caption_tail
                )
            else:
                bot.send_video(
                    chat_id,
                    f,
                    caption=(f"🎬 {title}\n⏱️ {duration}" if title else f"🎬\n⏱️ {duration}") + caption_tail,
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

# =========================
# DOWNLOAD FLOW
# =========================
def handle_download(chat_id, url, mode, status_msg_id, user_id):
    lock = get_lock(chat_id)
    if not lock.acquire(blocking=False):
        try:
            bot.edit_message_text("⚠️ انتظر، هناك تحميل شغال بالفعل...", chat_id, status_msg_id)
        except:
            pass
        return

    domain = get_domain(url)
    try:
        dl_id = f"{chat_id}:{int(time.time())}"
        active_downloads[chat_id] = {
            "proc": None,
            "cancel": threading.Event(),
            "dl_id": dl_id,
            "msg_id": status_msg_id
        }

        path, title, channel, duration, fail = ytdlp_download_with_progress(url, mode, chat_id, status_msg_id, dl_id, user_id)
        if fail:
            return

        if not path or not os.path.exists(path):
            try:
                bot.edit_message_text("DOWNLOAD_FAILED", chat_id, status_msg_id, reply_markup=start_keyboard(user_id))
            except:
                pass
            log_stat({"ts": time.time(), "type": "fail", "reason": "DOWNLOAD_FAILED", "chat_id": chat_id, "domain": domain})
            return

        send_result(chat_id, status_msg_id, path, mode, title, channel, duration)
        log_stat({
            "ts": time.time(),
            "type": "success",
            "chat_id": chat_id,
            "user_id": user_id,
            "domain": domain,
            "mode": mode,
            "title": title
        })

    finally:
        try:
            active_downloads.pop(chat_id, None)
        except:
            pass
        lock.release()

# =========================
# ADMIN STATE MACHINE
# =========================
admin_states = {}

def admin_set(step: str, data=None):
    admin_states[str(ADMIN_ID)] = {"step": step, "data": data or {}}

def admin_get():
    return admin_states.get(str(ADMIN_ID), {"step": None, "data": {}})

def admin_clear():
    admin_states.pop(str(ADMIN_ID), None)

# =========================
# REPORT (كل 12 ساعة)
# =========================
def build_report(hours=12):
    users = load_users()
    usage = load_usage()
    stats = _load_json(STATS_FILE, [])
    cutoff = time.time() - hours * 3600

    recent = [e for e in stats if e.get("ts", 0) >= cutoff]
    ok = sum(1 for e in recent if e.get("type") == "success")
    fail = sum(1 for e in recent if e.get("type") == "fail")
    canc = sum(1 for e in recent if e.get("type") == "cancel")

    dom = {}
    for e in recent:
        d = e.get("domain") or "unknown"
        dom[d] = dom.get(d, 0) + 1
    dom_sorted = sorted(dom.items(), key=lambda x: x[1], reverse=True)[:8]

    banned = sum(1 for u in users.values() if u.get("banned"))
    active_dl = len(active_downloads)

    today = datetime.utcnow().strftime("%Y-%m-%d")
    top_today = []
    for uid, days in usage.items():
        cnt = int(days.get(today, 0))
        if cnt:
            top_today.append((uid, cnt))
    top_today.sort(key=lambda x: x[1], reverse=True)
    top_today = top_today[:10]

    dom_lines = "\n".join([f"• {d}: <b>{c}</b>" for d, c in dom_sorted]) or "• لا يوجد"
    top_lines = "\n".join([f"• <code>{uid}</code>: <b>{cnt}</b>" for uid, cnt in top_today]) or "• لا يوجد"

    s = load_settings()
    forced = s.get("forced_channels") or []

    return (
        "📊 <b>تقرير استخدام البوت</b>\n"
        f"🕒 آخر <b>{hours}</b> ساعة\n\n"
        f"👥 المستخدمين: <b>{len(users)}</b>\n"
        f"🚫 المحظورين: <b>{banned}</b>\n"
        f"⬇️ تحميل ناجح: <b>{ok}</b>\n"
        f"❌ فشل: <b>{fail}</b>\n"
        f"🛑 إلغاء: <b>{canc}</b>\n"
        f"⚙️ تحميلات نشطة الآن: <b>{active_dl}</b>\n\n"
        "🌐 أكثر الدومينات:\n"
        f"{dom_lines}\n\n"
        "📌 الأعلى اليوم (حسب الروابط):\n"
        f"{top_lines}\n\n"
        "✅ الاشتراك الإجباري:\n"
        + ("• لا يوجد\n" if not forced else "\n".join([f"• {ch}" for ch in forced]))
    )

def report_loop():
    while True:
        try:
            if ADMIN_ID:
                bot.send_message(ADMIN_ID, build_report(12), reply_markup=start_keyboard(ADMIN_ID))
        except:
            pass
        time.sleep(12 * 3600)

# =========================
# BOT HANDLERS
# =========================
@bot.message_handler(commands=["start"])
def start(m):
    ensure_user(m)
    if is_banned(m.from_user.id):
        return

    if not bot_is_enabled_for(m.from_user.id):
        bot.send_message(m.chat.id, "⛔ البوت متوقف مؤقتاً.", reply_markup=start_keyboard(m.from_user.id))
        return

    s = load_settings()
    bot.send_message(m.chat.id, s["welcome_message"], reply_markup=start_keyboard(m.from_user.id))

@bot.message_handler(commands=["admin"])
def admin_cmd(m):
    if not is_admin(m.from_user.id):
        return
    admin_clear()
    bot.send_message(m.chat.id, "⚙️ <b>لوحة الأدمن</b>", reply_markup=admin_panel_kb())

@bot.message_handler(func=lambda m: True)
def any_text(m):
    ensure_user(m)

    if not bot_is_enabled_for(m.from_user.id):
        if not is_admin(m.from_user.id):
            bot.send_message(m.chat.id, "⛔ البوت متوقف مؤقتاً.", reply_markup=start_keyboard(m.from_user.id))
            return

    if is_banned(m.from_user.id):
        return

    s = load_settings()
    txt = (m.text or "").strip()

    if txt == s["buttons"]["start_btn"]:
        bot.send_message(m.chat.id, s["welcome_message"], reply_markup=start_keyboard(m.from_user.id))
        return

    if txt == s["buttons"]["admin_btn"] and is_admin(m.from_user.id):
        admin_clear()
        bot.send_message(m.chat.id, "⚙️ <b>لوحة الأدمن</b>", reply_markup=admin_panel_kb())
        return

    if is_admin(m.from_user.id):
        st = admin_get()
        step = st.get("step")
        if step:
            handle_admin_input(m, step, st.get("data", {}))
            return

    if not txt.startswith("http"):
        refuse_plain(m.chat.id, m.from_user.id)
        return

    url = normalize_url(txt)
    domain = get_domain(url)
    user_links[m.chat.id] = url

    if not check_forced_join(m.from_user.id):
        chans = load_settings().get("forced_channels") or []
        bot.send_message(
            m.chat.id,
            "🔒 لازم تشترك بالقناة/القنوات أولاً ثم اضغط ✅ تحقّق",
            reply_markup=force_join_kb(chans)
        )
        return

    ok, used, limit = daily_limit_ok(m.from_user.id)
    if not ok:
        bot.send_message(
            m.chat.id,
            f"⚠️ وصلت الحد اليومي.\n"
            f"استخدامك اليوم: <b>{used}</b> / <b>{limit}</b>",
            reply_markup=start_keyboard(m.from_user.id)
        )
        return

    kb = types.InlineKeyboardMarkup(row_width=1)
    if "instagram.com" in domain:
        kb.add(types.InlineKeyboardButton(load_settings()["buttons"]["ig_video"], callback_data="ig_video"))
    else:
        b = load_settings()["buttons"]
        kb.add(
            types.InlineKeyboardButton(b["clip"], callback_data="v_clip"),
            types.InlineKeyboardButton(b["audio_file"], callback_data="a_m4a"),
            types.InlineKeyboardButton(b["voice_note"], callback_data="a_voice"),
        )

    bot.reply_to(m, "اختر نوع التحميل 👇", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("force:check"))
def force_check(c):
    uid = c.from_user.id
    if check_forced_join(uid):
        bot.answer_callback_query(c.id, "✅ تم التحقق!")
        bot.send_message(c.message.chat.id, "✅ تقدر ترسل الرابط الآن.", reply_markup=start_keyboard(uid))
    else:
        bot.answer_callback_query(c.id, "❌ بعدك غير مشترك.")
        chans = load_settings().get("forced_channels") or []
        bot.send_message(
            c.message.chat.id,
            "🔒 لازم تشترك بالقناة/القنوات أولاً ثم اضغط ✅ تحقّق",
            reply_markup=force_join_kb(chans)
        )

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
        bot.edit_message_text("CANCELLED", chat_id, dl.get("msg_id", c.message.message_id), reply_markup=start_keyboard(c.from_user.id))
    except:
        pass

@bot.callback_query_handler(func=lambda c: c.data in ["ig_video", "v_clip", "a_m4a", "a_voice"])
def process_choice(c):
    chat_id = c.message.chat.id
    url = user_links.get(chat_id)
    uid = c.from_user.id

    inc_daily(uid)

    try:
        bot.delete_message(chat_id, c.message.message_id)
    except:
        pass

    msg = bot.send_message(chat_id, "⏳ بدء التحميل...")

    if not url:
        bot.edit_message_text("NO_URL", chat_id, msg.message_id, reply_markup=start_keyboard(uid))
        return

    mode = c.data
    t = threading.Thread(target=handle_download, args=(chat_id, url, mode, msg.message_id, uid), daemon=True)
    t.start()

# =========================
# ADMIN PANEL CALLBACKS + INPUT
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("adm:"))
def admin_actions(c):
    if not is_admin(c.from_user.id):
        return

    action = c.data.split(":", 1)[1]
    bot.answer_callback_query(c.id)

    if action == "welcome":
        admin_set("welcome")
        bot.send_message(c.message.chat.id, "✉️ ارسل <b>رسالة الترحيب الجديدة</b> الآن:")
        return

    if action == "ban":
        admin_set("ban")
        bot.send_message(c.message.chat.id, "🚫 ارسل ID المستخدم مع الأمر:\n<b>ban 123</b> أو <b>unban 123</b>")
        return

    if action == "buttons":
        admin_set("buttons")
        s = load_settings()
        b = s["buttons"]
        bot.send_message(
            c.message.chat.id,
            "🧷 ارسل صيغة تغيير الأزرار:\n"
            "<code>"
            "clip=نص\naudio_file=نص\nvoice_note=نص\n"
            "ig_video=نص\nstart_btn=نص\nadmin_btn=نص\ncancel=نص"
            "</code>\n\n"
            "📌 الحالي:\n"
            f"clip: {b['clip']}\n"
            f"audio_file: {b['audio_file']}\n"
            f"voice_note: {b['voice_note']}\n"
            f"ig_video: {b['ig_video']}\n"
            f"start_btn: {b['start_btn']}\n"
            f"admin_btn: {b['admin_btn']}\n"
            f"cancel: {b['cancel']}"
        )
        return

    if action == "broadcast":
        admin_set("broadcast")
        bot.send_message(c.message.chat.id, "📢 ارسل رسالة الإذاعة الآن (تروح لكل المستخدمين):")
        return

    if action == "force":
        admin_set("force")
        s = load_settings()
        forced = s.get("forced_channels") or []
        bot.send_message(
            c.message.chat.id,
            "✅ الاشتراك الإجباري:\n"
            f"{('• لا يوجد' if not forced else ('\n'.join(['• '+x for x in forced])))}\n\n"
            "اكتب:\n"
            "<code>add @channel</code> لإضافة\n"
            "<code>remove @channel</code> للحذف\n"
            "<code>clear</code> لمسح الكل"
        )
        return

    if action == "toggle":
        with settings_lock:
            s = load_settings()
            s["bot_enabled"] = not bool(s.get("bot_enabled", True))
            save_settings(s)
        bot.send_message(
            c.message.chat.id,
            f"⏸️ الحالة الآن: <b>{'شغال' if s['bot_enabled'] else 'متوقف'}</b>",
            reply_markup=admin_panel_kb()
        )
        return

    if action == "restart":
        bot.send_message(c.message.chat.id, "🔁 RESTARTING")
        try:
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except:
            bot.send_message(c.message.chat.id, "RESTART_FAILED")
        return

    if action == "report":
        bot.send_message(c.message.chat.id, build_report(12), reply_markup=admin_panel_kb())
        return

def handle_admin_input(m, step: str, data: dict):
    txt = (m.text or "").strip()

    if step == "welcome":
        with settings_lock:
            s = load_settings()
            s["welcome_message"] = txt
            save_settings(s)
        admin_clear()
        bot.send_message(m.chat.id, "✅ تم تحديث الترحيب.", reply_markup=admin_panel_kb())
        return

    if step == "ban":
        parts = txt.split()
        if len(parts) == 2 and parts[0].lower() in ("ban", "unban"):
            try:
                uid = int(parts[1])
                set_ban(uid, parts[0].lower() == "ban")
                admin_clear()
                bot.send_message(m.chat.id, "✅ تم.", reply_markup=admin_panel_kb())
            except:
                bot.send_message(m.chat.id, "INVALID_ID", reply_markup=admin_panel_kb())
        else:
            bot.send_message(m.chat.id, "INVALID_FORMAT", reply_markup=admin_panel_kb())
        return

    if step == "buttons":
        updates = {}
        for line in txt.splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k and v:
                updates[k] = v

        allowed = {"clip", "audio_file", "voice_note", "ig_video", "start_btn", "admin_btn", "cancel"}
        updates = {k: v for k, v in updates.items() if k in allowed}

        if not updates:
            bot.send_message(m.chat.id, "NO_CHANGES", reply_markup=admin_panel_kb())
            return

        with settings_lock:
            s = load_settings()
            s["buttons"].update(updates)
            save_settings(s)

        admin_clear()
        bot.send_message(m.chat.id, "✅ تم تحديث الأزرار.", reply_markup=admin_panel_kb())
        return

    if step == "broadcast":
        admin_clear()
        users = load_users()
        ok = 0
        fail = 0
        for uid_str, u in users.items():
            try:
                uid = int(uid_str)
                if u.get("banned"):
                    continue
                bot.send_message(uid, txt, reply_markup=start_keyboard(uid))
                ok += 1
            except:
                fail += 1
        bot.send_message(m.chat.id, f"📢 تم الإرسال.\n✅ وصل: <b>{ok}</b>\n❌ فشل: <b>{fail}</b>", reply_markup=admin_panel_kb())
        return

    if step == "force":
        with settings_lock:
            s = load_settings()
            forced = s.get("forced_channels") or []
            low = txt.lower().strip()

            if low == "clear":
                forced = []
            elif low.startswith("add "):
                ch = txt.split(" ", 1)[1].strip()
                if ch and not ch.startswith("@"):
                    ch = "@" + ch
                if ch and ch not in forced:
                    forced.append(ch)
            elif low.startswith("remove "):
                ch = txt.split(" ", 1)[1].strip()
                if ch and not ch.startswith("@"):
                    ch = "@" + ch
                forced = [x for x in forced if x != ch]
            else:
                bot.send_message(m.chat.id, "INVALID_FORMAT", reply_markup=admin_panel_kb())
                return

            s["forced_channels"] = forced
            save_settings(s)

        admin_clear()
        bot.send_message(m.chat.id, "✅ تم تحديث الاشتراك الإجباري.", reply_markup=admin_panel_kb())
        return

# =========================
# RUN BOT
# =========================
def run_bot():
    while True:
        try:
            bot.remove_webhook()
            bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
        except:
            time.sleep(5)

if __name__ == "__main__":
    if ADMIN_ID:
        threading.Thread(target=report_loop, daemon=True).start()

    print("Bot running 🔥")
    run_bot()
