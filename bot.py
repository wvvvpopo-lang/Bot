# -*- coding: utf-8 -*-
"""
ربات آپلود پک فیلم/عکس + سیستم اشتراک پریمیوم (عادی و طلایی) + عضویت اجباری
کتابخونه: pyTelegramBotAPI (telebot)
دیتابیس: SQLite

قبل از اجرا حتما این دو خط رو پر کن:
"""

import telebot
from telebot import types
import sqlite3
import os
import random
import string
import threading
import time
import re
from datetime import datetime, timedelta

# ============================== تنظیمات ==============================
BOT_TOKEN = "8658314282:AAGcVifNujg4R2XdIbhWZRiwyufKyHwmg1s"
MAIN_ADMIN_ID = 7837042019  # آیدی عددی ادمین اصلی رو اینجا بزار

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_data.db")

DURATIONS = {
    "یک روزه": timedelta(days=1),
    "یک هفته": timedelta(days=7),
    "یک ماهه": timedelta(days=30),
}

# state موقت کاربر برای گفتگوهای چند مرحله‌ای (فقط در حافظه)
user_states = {}

# ============================== دیتابیس ==============================
def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = db()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS admins (
                    user_id INTEGER PRIMARY KEY,
                    added_by INTEGER,
                    added_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS packs (
                    name TEXT PRIMARY KEY,
                    pack_type TEXT,
                    created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS pack_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pack_name TEXT,
                    file_type TEXT,
                    file_id TEXT,
                    file_order INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS subscriptions (
                    user_id INTEGER PRIMARY KEY,
                    sub_type TEXT,
                    is_golden INTEGER DEFAULT 0,
                    expiry TEXT,
                    active INTEGER DEFAULT 1,
                    notified INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS serials (
                    code TEXT PRIMARY KEY,
                    duration TEXT,
                    is_golden INTEGER DEFAULT 0,
                    created_by INTEGER,
                    used INTEGER DEFAULT 0,
                    used_by INTEGER,
                    created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS forced_channels (
                    channel_id TEXT PRIMARY KEY,
                    title TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS pending_serials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    requested_by INTEGER,
                    duration TEXT,
                    is_golden INTEGER,
                    status TEXT DEFAULT 'pending')""")
    conn.commit()
    conn.close()

    # ثبت ادمین اصلی
    conn = db()
    conn.execute("INSERT OR IGNORE INTO admins (user_id, added_by, added_at) VALUES (?,?,?)",
                 (MAIN_ADMIN_ID, MAIN_ADMIN_ID, str(datetime.now())))
    conn.commit()
    conn.close()


# ============================== توابع کمکی ==============================
def is_admin(user_id):
    conn = db()
    row = conn.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row is not None


def is_main_admin(user_id):
    return user_id == MAIN_ADMIN_ID


def get_all_admins():
    conn = db()
    rows = conn.execute("SELECT user_id FROM admins").fetchall()
    conn.close()
    return [r[0] for r in rows]


def generate_code():
    return "".join(random.choice(string.digits) for _ in range(12))


def get_forced_channels():
    conn = db()
    rows = conn.execute("SELECT channel_id, title FROM forced_channels").fetchall()
    conn.close()
    return rows


def get_subscription(user_id):
    conn = db()
    row = conn.execute("SELECT sub_type, is_golden, expiry, active FROM subscriptions WHERE user_id=?",
                        (user_id,)).fetchone()
    conn.close()
    return row


def is_premium(user_id):
    row = get_subscription(user_id)
    if not row:
        return False, False
    sub_type, is_golden, expiry, active = row
    if not active:
        return False, False
    if datetime.now() > datetime.fromisoformat(expiry):
        return False, False
    return True, bool(is_golden)


def check_force_sub(user_id):
    """برمی‌گردونه: (True/False کاربر عضو همه چنل‌هاست؟, لیست چنل‌های عضو نشده)"""
    _, golden = is_premium(user_id)
    if golden:
        return True, []
    channels = get_forced_channels()
    if not channels:
        return True, []
    not_joined = []
    for ch_id, title in channels:
        try:
            member = bot.get_chat_member(ch_id, user_id)
            if member.status in ("left", "kicked"):
                not_joined.append((ch_id, title))
        except Exception:
            not_joined.append((ch_id, title))
    return (len(not_joined) == 0), not_joined


def send_force_sub_message(chat_id, not_joined):
    markup = types.InlineKeyboardMarkup()
    for ch_id, title in not_joined:
        link = ch_id if str(ch_id).startswith("@") else str(ch_id)
        markup.add(types.InlineKeyboardButton(f"عضویت در {title}", url=f"https://t.me/{link.replace('@','')}"))
    markup.add(types.InlineKeyboardButton("✅ عضو شدم", callback_data="check_join"))
    bot.send_message(chat_id, "برای استفاده از ربات ابتدا باید در کانال‌های زیر عضو بشی:", reply_markup=markup)


def schedule_delete(chat_id, message_id, delay=20):
    def _del():
        time.sleep(delay)
        try:
            bot.delete_message(chat_id, message_id)
        except Exception:
            pass
    threading.Thread(target=_del, daemon=True).start()


def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("📥 دریافت پک"))
    markup.add(types.KeyboardButton("💳 وضعیت اشتراک"), types.KeyboardButton("📖 راهنما"))
    if is_admin(user_id):
        markup.add(types.KeyboardButton("🛠 پنل ادمین"))
    return markup


def admin_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("📤 آپلود پک فیلم"), types.KeyboardButton("📤 آپلود پک عکس"))
    markup.add(types.KeyboardButton("📤 آپلود پک عکس و فیلم"))
    markup.add(types.KeyboardButton("📋 لیست پک‌ها"))
    markup.add(types.KeyboardButton("🔑 ساخت سریال"))
    markup.add(types.KeyboardButton("📊 آمار کاربران پریمیوم"))
    markup.add(types.KeyboardButton("📡 مدیریت چنل‌های اجباری"))
    markup.add(types.KeyboardButton("⬅️ بازگشت به منو اصلی"))
    return markup


# ============================== شروع ==============================
@bot.message_handler(commands=["start"])
def cmd_start(message):
    bot.send_message(message.chat.id, "سلام! خوش اومدی 👋", reply_markup=main_menu(message.from_user.id))


@bot.message_handler(func=lambda m: m.text == "⬅️ بازگشت به منو اصلی")
def back_to_main(message):
    user_states.pop(message.from_user.id, None)
    bot.send_message(message.chat.id, "منو اصلی:", reply_markup=main_menu(message.from_user.id))


@bot.message_handler(func=lambda m: m.text == "🛠 پنل ادمین")
def open_admin_panel(message):
    if not is_admin(message.from_user.id):
        return
    bot.send_message(message.chat.id, "پنل ادمین:", reply_markup=admin_menu())


# ============================== راهنما ==============================
ADMIN_HELP = """<b>راهنمای ادمین</b>

📤 آپلود پک فیلم / عکس / عکس و فیلم — شروع فرآیند ساخت پک جدید
تمومه — پایان ارسال فایل‌ها برای پک در حال ساخت
📋 لیست پک‌ها — نمایش، ویرایش یا حذف پک‌ها
🔑 ساخت سریال — ساخت کد اشتراک عادی یا طلایی (نیاز به تایید ادمین اصلی دارد)
📊 آمار کاربران پریمیوم — لیست کاربران با اشتراک فعال
📡 مدیریت چنل‌های اجباری — افزودن/حذف چنل‌های عضویت اجباری
آیدی (عدد) ارتقا — ارتقای کاربر به ادمین (فقط ادمین اصلی)
"""

USER_HELP = """<b>راهنمای کاربر</b>

📥 دریافت پک — دریافت فایل‌های یک پک با اسمش
💳 وضعیت اشتراک — نمایش نوع و زمان باقی‌مانده اشتراک
برای فعال‌سازی اشتراک، کد ۱۲ رقمی که دریافت کردی رو همینجا بفرست.
"""


@bot.message_handler(func=lambda m: m.text == "📖 راهنما")
def show_help(message):
    if is_admin(message.from_user.id):
        bot.send_message(message.chat.id, ADMIN_HELP)
    else:
        bot.send_message(message.chat.id, USER_HELP)


# ============================== ارتقای ادمین ==============================
@bot.message_handler(regexp=r"^آیدی\s*\(\s*(\d+)\s*\)\s*ارتقا$")
def upgrade_admin(message):
    if not is_main_admin(message.from_user.id):
        return
    new_id = int(re.match(r"^آیدی\s*\(\s*(\d+)\s*\)\s*ارتقا$", message.text).group(1))
    conn = db()
    conn.execute("INSERT OR IGNORE INTO admins (user_id, added_by, added_at) VALUES (?,?,?)",
                 (new_id, message.from_user.id, str(datetime.now())))
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, f"کاربر {new_id} به عنوان ادمین اضافه شد ✅")
    try:
        bot.send_message(new_id, "🎉 تبریک! شما به عنوان ادمین ربات انتخاب شدید.")
    except Exception:
        pass


# ============================== آپلود پک ==============================
PACK_TYPE_MAP = {
    "📤 آپلود پک فیلم": "video",
    "📤 آپلود پک عکس": "photo",
    "📤 آپلود پک عکس و فیلم": "mixed",
}


@bot.message_handler(func=lambda m: m.text in PACK_TYPE_MAP)
def start_pack_upload(message):
    if not is_admin(message.from_user.id):
        return
    user_states[message.from_user.id] = {
        "action": "collecting_pack",
        "pack_type": PACK_TYPE_MAP[message.text],
        "files": [],  # list of (file_type, file_id)
        "edit_existing": None,
    }
    bot.send_message(message.chat.id, "فایل‌ها رو فوروارد/ارسال کن. وقتی تموم شد بنویس: تمومه")


@bot.message_handler(content_types=["photo", "video"])
def collect_pack_files(message):
    st = user_states.get(message.from_user.id)
    if not st or st.get("action") != "collecting_pack":
        return
    if message.content_type == "photo":
        file_id = message.photo[-1].file_id
        st["files"].append(("photo", file_id))
    elif message.content_type == "video":
        file_id = message.video.file_id
        st["files"].append(("video", file_id))
    bot.send_message(message.chat.id, f"دریافت شد ✅ (تعداد فایل‌ها تا الان: {len(st['files'])})")


@bot.message_handler(func=lambda m: m.text == "تمومه")
def finish_pack_upload(message):
    st = user_states.get(message.from_user.id)
    if not st or st.get("action") != "collecting_pack":
        return
    if not st["files"]:
        bot.send_message(message.chat.id, "هیچ فایلی دریافت نشد. لغو شد.")
        user_states.pop(message.from_user.id, None)
        return
    if st.get("edit_existing"):
        st["action"] = "adding_to_existing"
        save_pack_files(st["edit_existing"], st["files"], append=True)
        bot.send_message(message.chat.id, f"فایل‌های جدید به پک «{st['edit_existing']}» اضافه شد ✅",
                          reply_markup=admin_menu())
        user_states.pop(message.from_user.id, None)
        return
    user_states[message.from_user.id]["action"] = "waiting_pack_name"
    bot.send_message(message.chat.id, "اسم پک رو بنویس:")


def save_pack_files(pack_name, files, append=False):
    conn = db()
    now = str(datetime.now())
    if not append:
        conn.execute("DELETE FROM pack_files WHERE pack_name=?", (pack_name,))
        conn.execute("INSERT OR REPLACE INTO packs (name, pack_type, created_at) VALUES (?,?,?)",
                     (pack_name, "mixed", now))
        start_order = 0
    else:
        row = conn.execute("SELECT MAX(file_order) FROM pack_files WHERE pack_name=?", (pack_name,)).fetchone()
        start_order = (row[0] + 1) if row and row[0] is not None else 0
    for i, (ftype, fid) in enumerate(files):
        conn.execute("INSERT INTO pack_files (pack_name, file_type, file_id, file_order) VALUES (?,?,?,?)",
                     (pack_name, ftype, fid, start_order + i))
    conn.commit()
    conn.close()


@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get("action") == "waiting_pack_name")
def save_new_pack(message):
    st = user_states.get(message.from_user.id)
    pack_name = message.text.strip()
    conn = db()
    existing = conn.execute("SELECT name FROM packs WHERE name=?", (pack_name,)).fetchone()
    conn.close()
    save_pack_files(pack_name, st["files"], append=False)
    if existing:
        bot.send_message(message.chat.id, f"پک «{pack_name}» با فایل‌های جدید جایگزین شد ✅", reply_markup=admin_menu())
    else:
        bot.send_message(message.chat.id, f"پک «{pack_name}» ذخیره شد ✅", reply_markup=admin_menu())
    user_states.pop(message.from_user.id, None)


# ============================== لیست/ویرایش/حذف پک ==============================
@bot.message_handler(func=lambda m: m.text == "📋 لیست پک‌ها")
def list_packs(message):
    if not is_admin(message.from_user.id):
        return
    conn = db()
    rows = conn.execute("SELECT name FROM packs ORDER BY name").fetchall()
    conn.close()
    if not rows:
        bot.send_message(message.chat.id, "هیچ پکی ثبت نشده.")
        return
    markup = types.InlineKeyboardMarkup()
    for (name,) in rows:
        markup.add(types.InlineKeyboardButton(name, callback_data=f"pack_view:{name}"))
    bot.send_message(message.chat.id, "لیست پک‌ها:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("pack_view:"))
def pack_view(call):
    if not is_admin(call.from_user.id):
        return
    name = call.data.split(":", 1)[1]
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➕ افزودن فایل جدید", callback_data=f"pack_add:{name}"))
    markup.add(types.InlineKeyboardButton("🗑 حذف پک", callback_data=f"pack_del_ask:{name}"))
    bot.edit_message_text(f"پک: {name}", call.message.chat.id, call.message.message_id, reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("pack_add:"))
def pack_add(call):
    if not is_admin(call.from_user.id):
        return
    name = call.data.split(":", 1)[1]
    user_states[call.from_user.id] = {
        "action": "collecting_pack",
        "pack_type": "mixed",
        "files": [],
        "edit_existing": name,
    }
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, f"فایل‌های جدید برای پک «{name}» رو بفرست. وقتی تموم شد بنویس: تمومه")


@bot.callback_query_handler(func=lambda c: c.data.startswith("pack_del_ask:"))
def pack_del_ask(call):
    if not is_admin(call.from_user.id):
        return
    name = call.data.split(":", 1)[1]
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ بله، حذف کن", callback_data=f"pack_del_yes:{name}"),
               types.InlineKeyboardButton("❌ انصراف", callback_data=f"pack_del_no:{name}"))
    bot.edit_message_text(f"مطمئنی می‌خوای پک «{name}» رو حذف کنی؟", call.message.chat.id,
                          call.message.message_id, reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("pack_del_yes:"))
def pack_del_yes(call):
    if not is_admin(call.from_user.id):
        return
    name = call.data.split(":", 1)[1]
    conn = db()
    conn.execute("DELETE FROM packs WHERE name=?", (name,))
    conn.execute("DELETE FROM pack_files WHERE pack_name=?", (name,))
    conn.commit()
    conn.close()
    bot.edit_message_text(f"پک «{name}» حذف شد ✅", call.message.chat.id, call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("pack_del_no:"))
def pack_del_no(call):
    bot.answer_callback_query(call.id, "لغو شد")
    bot.edit_message_text("لغو شد.", call.message.chat.id, call.message.message_id)


# ============================== دریافت پک توسط کاربر ==============================
@bot.message_handler(func=lambda m: m.text == "📥 دریافت پک")
def ask_pack_name(message):
    user_states[message.from_user.id] = {"action": "waiting_pack_request"}
    bot.send_message(message.chat.id, "اسم پک مورد نظرت رو بفرست:")


@bot.message_handler(regexp=r"^دریافت پک (.+)$")
def receive_pack_command(message):
    name = re.match(r"^دریافت پک (.+)$", message.text).group(1).strip()
    deliver_pack(message.chat.id, message.from_user.id, name)


@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get("action") == "waiting_pack_request")
def receive_pack_name_flow(message):
    user_states.pop(message.from_user.id, None)
    deliver_pack(message.chat.id, message.from_user.id, message.text.strip())


def deliver_pack(chat_id, user_id, pack_name):
    ok, not_joined = check_force_sub(user_id)
    if not ok:
        send_force_sub_message(chat_id, not_joined)
        return

    conn = db()
    exists = conn.execute("SELECT name FROM packs WHERE name=?", (pack_name,)).fetchone()
    if not exists:
        conn.close()
        bot.send_message(chat_id, "پکی با این اسم پیدا نشد ❌")
        return
    files = conn.execute("SELECT file_type, file_id FROM pack_files WHERE pack_name=? ORDER BY file_order",
                          (pack_name,)).fetchall()
    conn.close()

    premium, golden = is_premium(user_id)

    if premium:
        to_send = files
    else:
        first_photo = next((f for f in files if f[0] == "photo"), None)
        first_video = next((f for f in files if f[0] == "video"), None)
        to_send = [f for f in (first_photo, first_video) if f]
        if not to_send:
            to_send = files[:1]

    sent_msgs = []
    for ftype, fid in to_send:
        if ftype == "photo":
            m = bot.send_photo(chat_id, fid)
        else:
            m = bot.send_video(chat_id, fid)
        sent_msgs.append(m)

    if not premium:
        bot.send_message(chat_id, "⚠️ این فقط پیش‌نمایشه. برای دریافت کامل پک، اشتراک پریمیوم تهیه کن.")

    for m in sent_msgs:
        schedule_delete(chat_id, m.message_id, 20)


@bot.callback_query_handler(func=lambda c: c.data == "check_join")
def check_join_callback(call):
    ok, not_joined = check_force_sub(call.from_user.id)
    if ok:
        bot.answer_callback_query(call.id, "عضویت تایید شد ✅")
        bot.edit_message_text("عضویت شما تایید شد. حالا می‌تونی از ربات استفاده کنی ✅",
                              call.message.chat.id, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, "هنوز عضو همه چنل‌ها نشدی ❌", show_alert=True)


# ============================== ساخت سریال ==============================
@bot.message_handler(func=lambda m: m.text == "🔑 ساخت سریال")
def serial_type_select(message):
    if not is_admin(message.from_user.id):
        return
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("اشتراک عادی", callback_data="serial_kind:normal"),
               types.InlineKeyboardButton("اشتراک طلایی 🥇", callback_data="serial_kind:golden"))
    bot.send_message(message.chat.id, "نوع اشتراک رو انتخاب کن:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("serial_kind:"))
def serial_duration_select(call):
    kind = call.data.split(":", 1)[1]
    markup = types.InlineKeyboardMarkup()
    for d in DURATIONS:
        markup.add(types.InlineKeyboardButton(d, callback_data=f"serial_dur:{kind}:{d}"))
    bot.edit_message_text("مدت زمان رو انتخاب کن:", call.message.chat.id, call.message.message_id, reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("serial_dur:"))
def serial_request(call):
    _, kind, duration = call.data.split(":")
    is_golden = 1 if kind == "golden" else 0
    requester = call.from_user.id

    if is_main_admin(requester):
        code = create_serial(duration, is_golden, requester)
        bot.edit_message_text(f"کد سریال ساخته شد:\n<code>{code}</code>", call.message.chat.id,
                              call.message.message_id)
        return

    conn = db()
    cur = conn.execute("INSERT INTO pending_serials (requested_by, duration, is_golden, status) VALUES (?,?,?,?)",
                       (requester, duration, is_golden, "pending"))
    pending_id = cur.lastrowid
    conn.commit()
    conn.close()

    bot.edit_message_text("درخواست ساخت سریال برای ادمین اصلی ارسال شد. منتظر تایید بمون.", call.message.chat.id,
                          call.message.message_id)

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ تایید", callback_data=f"serial_approve:{pending_id}"),
               types.InlineKeyboardButton("❌ رد", callback_data=f"serial_reject:{pending_id}"))
    kind_fa = "طلایی 🥇" if is_golden else "عادی"
    try:
        bot.send_message(MAIN_ADMIN_ID,
                          f"درخواست ساخت سریال از ادمین {requester}\nنوع: {kind_fa}\nمدت: {duration}",
                          reply_markup=markup)
    except Exception:
        pass


def create_serial(duration, is_golden, created_by):
    code = generate_code()
    conn = db()
    conn.execute("INSERT INTO serials (code, duration, is_golden, created_by, used, created_at) VALUES (?,?,?,?,0,?)",
                 (code, duration, is_golden, created_by, str(datetime.now())))
    conn.commit()
    conn.close()
    return code


@bot.callback_query_handler(func=lambda c: c.data.startswith("serial_approve:"))
def serial_approve(call):
    if not is_main_admin(call.from_user.id):
        return
    pending_id = int(call.data.split(":", 1)[1])
    conn = db()
    row = conn.execute("SELECT requested_by, duration, is_golden, status FROM pending_serials WHERE id=?",
                       (pending_id,)).fetchone()
    if not row or row[3] != "pending":
        conn.close()
        bot.answer_callback_query(call.id, "این درخواست قبلا پردازش شده.")
        return
    requested_by, duration, is_golden, _ = row
    conn.execute("UPDATE pending_serials SET status='approved' WHERE id=?", (pending_id,))
    conn.commit()
    conn.close()

    code = create_serial(duration, is_golden, requested_by)
    bot.edit_message_text("تایید شد ✅", call.message.chat.id, call.message.message_id)
    try:
        bot.send_message(requested_by, f"درخواست سریالت تایید شد ✅\nکد سریال:\n<code>{code}</code>")
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("serial_reject:"))
def serial_reject(call):
    if not is_main_admin(call.from_user.id):
        return
    pending_id = int(call.data.split(":", 1)[1])
    conn = db()
    row = conn.execute("SELECT requested_by, status FROM pending_serials WHERE id=?", (pending_id,)).fetchone()
    if not row or row[1] != "pending":
        conn.close()
        bot.answer_callback_query(call.id, "این درخواست قبلا پردازش شده.")
        return
    requested_by = row[0]
    conn.execute("UPDATE pending_serials SET status='rejected' WHERE id=?", (pending_id,))
    conn.commit()
    conn.close()
    bot.edit_message_text("رد شد ❌", call.message.chat.id, call.message.message_id)
    try:
        bot.send_message(requested_by, "درخواست ساخت سریالت توسط ادمین اصلی رد شد ❌")
    except Exception:
        pass


# ============================== فعال‌سازی کد توسط کاربر ==============================
@bot.message_handler(func=lambda m: m.chat.type == "private" and re.fullmatch(r"\d{12}", m.text or ""))
def activate_code(message):
    code = message.text.strip()
    conn = db()
    row = conn.execute("SELECT duration, is_golden, created_by, used FROM serials WHERE code=?", (code,)).fetchone()
    if not row:
        conn.close()
        bot.send_message(message.chat.id, "کد نامعتبره ❌")
        return
    duration, is_golden, created_by, used = row
    if used:
        conn.close()
        bot.send_message(message.chat.id, "این کد قبلا استفاده شده ❌")
        return

    expiry = datetime.now() + DURATIONS[duration]
    conn.execute("""INSERT INTO subscriptions (user_id, sub_type, is_golden, expiry, active, notified)
                    VALUES (?,?,?,?,1,0)
                    ON CONFLICT(user_id) DO UPDATE SET
                        sub_type=excluded.sub_type, is_golden=excluded.is_golden,
                        expiry=excluded.expiry, active=1, notified=0""",
                 (message.from_user.id, duration, is_golden, expiry.isoformat()))
    conn.execute("UPDATE serials SET used=1, used_by=? WHERE code=?", (message.from_user.id, code))
    conn.commit()
    conn.close()

    kind_fa = "طلایی 🥇" if is_golden else "عادی"
    bot.send_message(message.chat.id, f"اشتراک {kind_fa} با موفقیت فعال شد ✅\nمدت: {duration}")

    notify_ids = {created_by, MAIN_ADMIN_ID}
    for admin_id in notify_ids:
        try:
            bot.send_message(admin_id, f"کد سریال (<code>{code}</code>) توسط کاربر {message.from_user.id} استفاده شد.")
        except Exception:
            pass


# ============================== وضعیت اشتراک ==============================
@bot.message_handler(func=lambda m: m.text == "💳 وضعیت اشتراک")
def subscription_status(message):
    row = get_subscription(message.from_user.id)
    if not row:
        bot.send_message(message.chat.id, "شما در حال حاضر اشتراک فعالی ندارید.")
        return
    sub_type, is_golden, expiry, active = row
    expiry_dt = datetime.fromisoformat(expiry)
    now = datetime.now()
    if not active or now > expiry_dt:
        bot.send_message(message.chat.id, "شما در حال حاضر اشتراک فعالی ندارید.")
        return
    remaining = expiry_dt - now
    days = remaining.days
    hours = remaining.seconds // 3600
    minutes = (remaining.seconds % 3600) // 60
    kind_fa = "طلایی 🥇" if is_golden else "عادی"
    bot.send_message(message.chat.id,
                      f"نوع اشتراک: {kind_fa}\nمدت خریداری‌شده: {sub_type}\n"
                      f"زمان باقی‌مانده: {days} روز, {hours} ساعت, {minutes} دقیقه")


# ============================== آمار کاربران پریمیوم ==============================
@bot.message_handler(func=lambda m: m.text == "📊 آمار کاربران پریمیوم")
def premium_stats(message):
    if not is_admin(message.from_user.id):
        return
    conn = db()
    rows = conn.execute("SELECT user_id, sub_type, is_golden, expiry, active FROM subscriptions").fetchall()
    conn.close()
    now = datetime.now()
    active_rows = [r for r in rows if r[4] and datetime.fromisoformat(r[3]) > now]
    if not active_rows:
        bot.send_message(message.chat.id, "در حال حاضر هیچ کاربر پریمیوم فعالی وجود نداره.")
        return
    text = f"تعداد کاربران پریمیوم فعال: {len(active_rows)}\n\n"
    for user_id, sub_type, is_golden, expiry, active in active_rows:
        kind_fa = "طلایی" if is_golden else "عادی"
        expiry_fa = datetime.fromisoformat(expiry).strftime("%Y-%m-%d %H:%M")
        text += f"👤 {user_id} | {kind_fa} | {sub_type} | تا {expiry_fa}\n"
    bot.send_message(message.chat.id, text)


# ============================== مدیریت چنل‌های اجباری ==============================
@bot.message_handler(func=lambda m: m.text == "📡 مدیریت چنل‌های اجباری")
def manage_channels(message):
    if not is_admin(message.from_user.id):
        return
    channels = get_forced_channels()
    markup = types.InlineKeyboardMarkup()
    for ch_id, title in channels:
        markup.add(types.InlineKeyboardButton(f"🗑 حذف {title}", callback_data=f"ch_del:{ch_id}"))
    markup.add(types.InlineKeyboardButton("➕ افزودن چنل جدید", callback_data="ch_add"))
    text = "چنل‌های عضویت اجباری فعلی:\n" + "\n".join([f"- {t} ({i})" for i, t in channels]) if channels else \
        "هیچ چنلی ثبت نشده."
    bot.send_message(message.chat.id, text, reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data == "ch_add")
def ch_add_start(call):
    if not is_admin(call.from_user.id):
        return
    user_states[call.from_user.id] = {"action": "waiting_channel_add"}
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id,
                      "آیدی عددی چنل یا یوزرنیم (@channel) رو بفرست.\n"
                      "توجه: ربات باید ادمین اون چنل باشه.")


@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get("action") == "waiting_channel_add")
def ch_add_finish(message):
    user_states.pop(message.from_user.id, None)
    ch_input = message.text.strip()
    try:
        chat = bot.get_chat(ch_input)
        title = chat.title or ch_input
        ch_id = f"@{chat.username}" if chat.username else str(chat.id)
    except Exception:
        bot.send_message(message.chat.id, "نتونستم این چنل رو پیدا کنم. مطمئن شو ربات توش ادمینه.")
        return
    conn = db()
    conn.execute("INSERT OR REPLACE INTO forced_channels (channel_id, title) VALUES (?,?)", (ch_id, title))
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, f"چنل «{title}» به لیست عضویت اجباری اضافه شد ✅")


@bot.callback_query_handler(func=lambda c: c.data.startswith("ch_del:"))
def ch_del(call):
    if not is_admin(call.from_user.id):
        return
    ch_id = call.data.split(":", 1)[1]
    conn = db()
    conn.execute("DELETE FROM forced_channels WHERE channel_id=?", (ch_id,))
    conn.commit()
    conn.close()
    bot.answer_callback_query(call.id, "حذف شد ✅")
    bot.edit_message_text("چنل حذف شد ✅", call.message.chat.id, call.message.message_id)


# ============================== چک خودکار انقضای اشتراک ==============================
def expiry_checker_loop():
    while True:
        try:
            conn = db()
            now = datetime.now()
            rows = conn.execute("SELECT user_id, expiry FROM subscriptions WHERE active=1 AND notified=0").fetchall()
            for user_id, expiry in rows:
                if now > datetime.fromisoformat(expiry):
                    conn.execute("UPDATE subscriptions SET active=0, notified=1 WHERE user_id=?", (user_id,))
                    try:
                        bot.send_message(user_id, "⏰ اشتراک پریمیوم شما به پایان رسید.")
                    except Exception:
                        pass
            conn.commit()
            conn.close()
        except Exception:
            pass
        time.sleep(15)


# ============================== اجرا ==============================
if __name__ == "__main__":
    init_db()
    threading.Thread(target=expiry_checker_loop, daemon=True).start()
    print("ربات اجرا شد...")
    bot.infinity_polling(skip_pending=True)
