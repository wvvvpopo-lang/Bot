import logging
import random
import json
import os
import time
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

# ==================== تنظیمات ====================
BOT_TOKEN = "8109899106:AAEfYzpVUq6S6Fbs_7BRMgbIN0JN0rqeiic"
ADMIN_IDS = [7837042019]
BOT_OWNER_ID = 7837042019 # ← آیدی مالک ربات (همون ادمین اصلی)
BOT_NAME_TRIGGERS = ["ربی", "ربات", "bot", "بات"]  # کلماتی که ربات جواب میده
DATA_FILE = "users_data.json"
CHALLENGES_FILE = "challenges.json"
SERIALS_FILE = "serials.json"
START_COINS = 1000
MAX_MINER_LEVEL = 1000

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== ابزارها ====================
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_challenges():
    if os.path.exists(CHALLENGES_FILE):
        with open(CHALLENGES_FILE, "r") as f:
            return json.load(f)
    return {}

def save_challenges(challenges):
    with open(CHALLENGES_FILE, "w") as f:
        json.dump(challenges, f, ensure_ascii=False, indent=2)

def load_serials():
    if os.path.exists(SERIALS_FILE):
        with open(SERIALS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_serials(serials):
    with open(SERIALS_FILE, "w") as f:
        json.dump(serials, f, ensure_ascii=False, indent=2)

def get_user(user_id: str, data: dict) -> dict:
    if user_id not in data:
        data[user_id] = {
            "coins": 0,
            "registered": False,
            "miner_level": 0,
            "miner_last_claim": 0,
            "max_coins": 0,
            "wheel_last_spin": 0,
            "username": ""
        }
    u = data[user_id]
    for key, default in [
        ("miner_level", 0), ("miner_last_claim", 0),
        ("max_coins", 0), ("wheel_last_spin", 0), ("username", "")
    ]:
        if key not in u:
            u[key] = default
    if u.get("coins", 0) > u.get("max_coins", 0):
        u["max_coins"] = u["coins"]
    return u

def is_admin(user_id: str) -> bool:
    return int(user_id) in ADMIN_IDS

def format_coins(n: int) -> str:
    if n >= 1_000_000_000:
        v = n / 1_000_000_000
        return f"{v:.2f}".rstrip('0').rstrip('.') + " بیل"
    if n >= 1_000_000:
        v = n / 1_000_000
        return f"{v:.2f}".rstrip('0').rstrip('.') + " میل"
    if n >= 1_000:
        v = n / 1_000
        return f"{v:.2f}".rstrip('0').rstrip('.') + " کا"
    return str(n)

def parse_amount(text: str) -> int:
    text = text.strip().lower().replace(",", "")
    fa_to_en = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
    text = text.translate(fa_to_en)
    try:
        if "بیل" in text or "bil" in text:
            num = re.sub(r'[^\d.]', '', text)
            return int(float(num) * 1_000_000_000)
        if "میل" in text or "mil" in text:
            num = re.sub(r'[^\d.]', '', text)
            return int(float(num) * 1_000_000)
        if "کا" in text or "ka" in text or text.endswith("k"):
            num = re.sub(r'[^\d.]', '', text)
            return int(float(num) * 1_000)
        return int(float(text))
    except:
        return -1

def miner_upgrade_cost(level: int) -> int:
    base = 199_000
    return int(base * (1.4 ** level))

def miner_hourly_income(level: int) -> int:
    if level == 0:
        return 0
    cost = miner_upgrade_cost(level - 1)
    return int(cost * 0.10)

def miner_pending_coins(user: dict) -> int:
    level = user.get('miner_level', 0)
    if level == 0:
        return 0
    last_claim = user.get('miner_last_claim', 0)
    now = time.time()
    hours_passed = (now - last_claim) / 3600
    hourly = miner_hourly_income(level)
    return int(hours_passed * hourly)

def generate_serial() -> str:
    return ''.join([str(random.randint(0, 9)) for _ in range(11)])

# ==================== گردونه شانس ====================
WHEEL_PRIZES = [
    (1_000_000_000, 0.0000001, "👑 ۱ بیل - جکپات!!!"),
    (500_000_000,   0.0000009, "💎 ۵۰۰ میل"),
    (200_000_000,   0.000002,  "💎 ۲۰۰ میل"),
    (100_000_000,   0.000007,  "🌟 ۱۰۰ میل"),
    (50_000_000,    0.00002,   "🌟 ۵۰ میل"),
    (20_000_000,    0.0001,    "⭐ ۲۰ میل"),
    (10_000_000,    0.0005,    "⭐ ۱۰ میل"),
    (5_000_000,     0.002,     "💰 ۵ میل"),
    (2_000_000,     0.01,      "💰 ۲ میل"),
    (1_000_000,     0.05,      "💰 ۱ میل"),
    (500_000,       0.1,       "🪙 ۵۰۰ کا"),
    (200_000,       0.2,       "🪙 ۲۰۰ کا"),
    (100_000,       0.3,       "🪙 ۱۰۰ کا"),
    (50_000,        0.3369989, "🪙 ۵۰ کا"),
]

def spin_wheel():
    d1 = random.randint(1, 6)
    d2 = random.randint(1, 6)
    d3 = random.randint(1, 6)
    prizes = [p[0] for p in WHEEL_PRIZES]
    weights = [p[1] for p in WHEEL_PRIZES]
    labels = [p[2] for p in WHEEL_PRIZES]
    chosen_idx = random.choices(range(len(prizes)), weights=weights, k=1)[0]
    prize = prizes[chosen_idx]
    label = labels[chosen_idx]
    triple = (d1 == d2 == d3)
    if triple:
        prize = min(prize * 3, 1_000_000_000)
    return d1, d2, d3, prize, label, triple

def can_spin_wheel(user: dict) -> tuple:
    last = user.get("wheel_last_spin", 0)
    elapsed = time.time() - last
    wait = 86400 - elapsed
    if wait <= 0:
        return True, 0
    return False, int(wait)

def seconds_to_persian(secs: int) -> str:
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    parts = []
    if h: parts.append(f"{h} ساعت")
    if m: parts.append(f"{m} دقیقه")
    if s: parts.append(f"{s} ثانیه")
    return " و ".join(parts) if parts else "چند ثانیه"

DICE_MULTIPLIERS = [2, 4, 8, 16]

GREETING_RESPONSES = [
    "سلام عزیزم! 😊 چطور می‌تونم کمکت کنم؟",
    "سلام سلام! 🎉 خوش اومدی!",
    "درود دوست عزیز! 😄",
    "هی هی! سلام 👋",
    "سلام! حالت خوبه؟ 😊",
]

def detect_bet_command(text: str):
    original = text.strip()
    fa_to_en = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
    text_en = original.translate(fa_to_en)

    if "شرط" not in original:
        return None

    if "فرد" in original:
        choice = "fard"
    elif "زوج" in original:
        choice = "zoj"
    else:
        return None

    amount_match = re.search(
        r'(\d+(?:\.\d+)?)\s*(بیل|میل|کا)',
        text_en,
        re.IGNORECASE
    )
    if amount_match:
        num_str = amount_match.group(1)
        unit = amount_match.group(2)
        amount = parse_amount(num_str + unit)
    else:
        num_match = re.search(r'(\d+)', text_en)
        if num_match:
            amount = int(num_match.group(1))
        else:
            return None

    if amount <= 0:
        return None

    return ("zojfard", amount, choice)

# ==================== تشخیص چلنج تاس ====================
def detect_challenge_command(text: str):
    """
    فرمت: چلنج تاس (مقدار)
    مثال: چلنج تاس ۱۰میل  یا  چلنج تاس 500کا
    """
    original = text.strip()
    fa_to_en = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
    text_en = original.translate(fa_to_en)

    if "چلنج" not in original or "تاس" not in original:
        return None

    amount_match = re.search(
        r'(\d+(?:\.\d+)?)\s*(بیل|میل|کا)',
        text_en,
        re.IGNORECASE
    )
    if amount_match:
        num_str = amount_match.group(1)
        unit = amount_match.group(2)
        amount = parse_amount(num_str + unit)
    else:
        num_match = re.search(r'(\d+)', text_en)
        if num_match:
            amount = int(num_match.group(1))
        else:
            return None

    if amount <= 0:
        return None

    return amount

# ==================== تشخیص دستور سریال ماینر ====================
def detect_serial_command(text: str):
    """
    فرمت: ساخت سریال ماینر [تعداد] عدد[مقدار]
    مثال: ساخت سریال ماینر 5 عدد 10کا
    """
    original = text.strip()
    fa_to_en = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
    text_en = original.translate(fa_to_en)

    if "ساخت سریال ماینر" not in original:
        return None

    count_match = re.search(r'(\d+)\s*عدد', text_en)
    if not count_match:
        return None
    count = int(count_match.group(1))

    amount_match = re.search(
        r'(\d+(?:\.\d+)?)\s*(بیل|میل|کا)',
        text_en,
        re.IGNORECASE
    )
    if amount_match:
        num_str = amount_match.group(1)
        unit = amount_match.group(2)
        coin_per_serial = parse_amount(num_str + unit)
    else:
        num_match = re.search(r'عدد\s*(\d+)', text_en)
        if num_match:
            coin_per_serial = int(num_match.group(1))
        else:
            return None

    if count <= 0 or coin_per_serial <= 0:
        return None

    return (count, coin_per_serial)

# ==================== دستورات ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    first_name = update.effective_user.first_name
    username = update.effective_user.username or ""
    data = load_data()
    user = get_user(user_id, data)
    user["username"] = username

    guide = (
        "━━━━━━━━━━━━━━━━━━\n"
        "🎮 *راهنمای کامل ربات*\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "📝 *دستورات فارسی:*\n"
        "• بنویس *موجودی* ← موجودی و رکورد\n"
        "• بنویس *پروفیت* ← اطلاعات ماینر\n"
        "• بنویس *گردونه* ← گردونه شانس\n"
        "• بنویس *ماینر* ← پنل ماینر\n"
        "• بنویس *تاس* ← بازی تاس\n"
        "• بنویس *منو* ← منوی اصلی\n"
        "• بنویس *پولداران* ← ۱۰ ثروتمند برتر\n\n"
        "🎲 *شرط‌بندی با متن:*\n"
        "• شرط ۱۰ میل فرد\n"
        "• شرط ۵۰۰ کا زوج\n\n"
        "🏆 *چلنج تاس:*\n"
        "• چلنج تاس ۱۰میل ← ایجاد چلنج\n"
        "• قبول میکنم چلنجتو ← پذیرش چلنج\n"
        "• شروع ← پرتاب تاس (نفر اول)\n"
        "هر کی جمع دو تاسش بیشتر بود برنده!\n\n"
        "🎰 *تاس:*\n"
        "عدد تصادفی ۱-۱۰۰ داده میشه\n"
        "ضریب انتخاب کن → حداکثر x16\n\n"
        "🎡 *گردونه شانس:*\n"
        "روزی یک‌بار! جایزه تا ۱ بیل!\n\n"
        "⛏ *ماینر:*\n"
        "• بنویس *جمع‌آوری* ← برداشت کوین\n"
        "• ساخت سریال ماینر ۵ عدد ۱۰کا ← سریال هدیه\n\n"
        "🎁 *گیفت:*\n"
        "• /gift مقدار آیدی\n"
        "• /mgift لول آیدی\n\n"
        "💱 *واحدها:* کا=هزار | میل=میلیون | بیل=میلیارد\n"
        "━━━━━━━━━━━━━━━━━━"
    )

    if user["registered"]:
        await update.message.reply_text(
            f"👋 سلام {first_name}!\n"
            f"💰 موجودی: {format_coins(user['coins'])} کوین\n"
            f"⛏ ماینر: لول {user['miner_level']}\n\n"
            f"{guide}",
            parse_mode="Markdown"
        )
    else:
        user["coins"] = START_COINS
        user["max_coins"] = START_COINS
        user["registered"] = True
        save_data(data)
        await update.message.reply_text(
            f"🎉 خوش اومدی {first_name}!\n"
            f"💰 {START_COINS} کوین رایگان گرفتی!\n\n"
            f"{guide}",
            parse_mode="Markdown"
        )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = load_data()
    user = get_user(user_id, data)
    if not user["registered"]:
        await update.message.reply_text("❌ اول /start بزن!")
        return
    await show_main_menu_msg(update.message, user, user_id, is_admin(user_id))

async def show_main_menu_msg(msg, user, user_id, admin=False, edit=False):
    keyboard = [
        [
            InlineKeyboardButton("🎲 زوج و فرد", callback_data="game_zojfard"),
            InlineKeyboardButton("🎰 تاس", callback_data="game_dice"),
        ],
        [
            InlineKeyboardButton("🎡 گردونه شانس", callback_data="game_wheel"),
            InlineKeyboardButton("⛏ ماینر", callback_data="miner_menu"),
        ],
        [
            InlineKeyboardButton("💰 موجودی", callback_data="balance"),
            InlineKeyboardButton("📈 پروفیت", callback_data="profit"),
        ],
        [
            InlineKeyboardButton("🏆 پولداران", callback_data="leaderboard"),
        ],
    ]
    if admin:
        keyboard.append([InlineKeyboardButton("👑 پنل ادمین", callback_data="admin_panel")])

    text = (
        f"🎮 *منوی اصلی*\n\n"
        f"💰 موجودی: {format_coins(user['coins'])} کوین\n"
        f"⛏ ماینر: لول {user['miner_level']}\n\n"
        f"چی می‌خوای؟"
    )
    if edit:
        await msg.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await msg.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_balance(update.message, update.effective_user)

async def show_balance(msg, tg_user):
    user_id = str(tg_user.id)
    data = load_data()
    user = get_user(user_id, data)
    if not user["registered"]:
        await msg.reply_text("❌ اول /start بزن!")
        return
    username = user.get("username", "") or tg_user.username or ""
    id_display = f"@{username}" if username else f"#{user_id}"
    if user["coins"] > user.get("max_coins", 0):
        user["max_coins"] = user["coins"]
        data[user_id] = user
        save_data(data)
    await msg.reply_text(
        f"👤 *اطلاعات کاربر*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🆔 کاربر عزیز با آیدی {id_display}\n\n"
        f"💰 موجودی شما: *{format_coins(user['coins'])}* کوین\n"
        f"⛏ لول ماینر شما: *{user['miner_level']}*\n"
        f"🏆 رکورد بیشترین موجودی: *{format_coins(user['max_coins'])}* کوین\n"
        f"━━━━━━━━━━━━━━━",
        parse_mode="Markdown"
    )

async def profit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_profit(update.message, update.effective_user)

async def show_profit(msg, tg_user):
    user_id = str(tg_user.id)
    data = load_data()
    user = get_user(user_id, data)
    if not user["registered"]:
        await msg.reply_text("❌ اول /start بزن!")
        return
    level = user["miner_level"]
    hourly = miner_hourly_income(level)
    pending = miner_pending_coins(user)
    if level < MAX_MINER_LEVEL:
        next_hourly = miner_hourly_income(level + 1)
        next_cost = miner_upgrade_cost(level)
        next_info = (
            f"⬆️ پروفیت ماینر لول {level+1}: *{format_coins(next_hourly)}* در ساعت\n"
            f"💵 هزینه ارتقا: *{format_coins(next_cost)}* کوین"
        )
    else:
        next_info = "🏆 ماینر به ماکزیمم لول رسیده!"
    await msg.reply_text(
        f"📈 *پروفیت شما به شرح زیر می‌باشد*\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"⛏ لول ماینر شما: *{level}*\n\n"
        f"⏱ یک ساعت: *{format_coins(hourly)}* کوین\n"
        f"🕐 کوین جمع‌شده تا به الان: *{format_coins(pending)}* کوین\n\n"
        f"{next_info}\n"
        f"━━━━━━━━━━━━━━━",
        parse_mode="Markdown"
    )

# ==================== لیدربورد ====================
async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_leaderboard(update.message)

async def show_leaderboard(msg):
    data = load_data()
    registered = [
        (uid, u) for uid, u in data.items()
        if u.get("registered") and u.get("coins", 0) > 0
    ]
    top10 = sorted(registered, key=lambda x: x[1].get("coins", 0), reverse=True)[:10]

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    lines = ["🏆 *ثروتمندترین‌های ربات*\n━━━━━━━━━━━━━━━\n"]
    for i, (uid, u) in enumerate(top10):
        username = u.get("username", "")
        name = f"@{username}" if username else f"کاربر {uid[-4:]}"
        coins = format_coins(u.get("coins", 0))
        lines.append(f"{medals[i]} {name}: *{coins}* کوین")

    if not top10:
        lines.append("هنوز کسی ثبت‌نام نکرده!")

    lines.append("\n━━━━━━━━━━━━━━━")
    await msg.reply_text("\n".join(lines), parse_mode="Markdown")

# ==================== گردونه شانس ====================
async def wheel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = load_data()
    user = get_user(user_id, data)
    if not user["registered"]:
        await update.message.reply_text("❌ اول /start بزن!")
        return
    await show_wheel(update.message, user, edit=False)

async def show_wheel(msg, user, edit=False):
    can, wait_secs = can_spin_wheel(user)
    if can:
        keyboard = [[InlineKeyboardButton("🎡 بچرخون! (رایگان)", callback_data="wheel_spin")]]
        text = (
            f"🎡 *گردونه شانس*\n\n"
            f"💰 موجودی: {format_coins(user['coins'])} کوین\n\n"
            f"🎲 سه تاس پرتاب میشه!\n"
            f"🔥 سه‌تایی = جایزه ۳ برابر!\n"
            f"👑 حداکثر جایزه: ۱ بیل!\n"
            f"⏰ روزی یک‌بار می‌تونی بچرخونی\n\n"
            f"✅ آماده‌ای؟ بزن بچرخه!"
        )
    else:
        wait_text = seconds_to_persian(wait_secs)
        keyboard = [[InlineKeyboardButton("🔙 برگشت", callback_data="main_menu")]]
        text = (
            f"🎡 *گردونه شانس*\n\n"
            f"⏳ باید صبر کنی!\n\n"
            f"⏰ تا چرخش بعدی: *{wait_text}*\n\n"
            f"روزی یک‌بار می‌تونی بچرخونی 😊"
        )
    if edit:
        await msg.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await msg.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# ==================== ماینر ====================
async def miner_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = load_data()
    user = get_user(user_id, data)
    if not user["registered"]:
        await update.message.reply_text("❌ اول /start بزن!")
        return
    await show_miner(update.message, user, user_id, edit=False)

async def show_miner(msg_or_query, user, user_id, edit=False):
    level = user["miner_level"]
    hourly = miner_hourly_income(level)
    pending = miner_pending_coins(user)
    keyboard = []
    if level < MAX_MINER_LEVEL:
        next_cost = miner_upgrade_cost(level)
        upgrade_text = f"💵 هزینه ارتقا به لول {level+1}: {format_coins(next_cost)} کوین"
        keyboard.append([InlineKeyboardButton(
            f"⬆️ ارتقا → لول {level+1} ({format_coins(next_cost)} 🪙)",
            callback_data="miner_upgrade"
        )])
    else:
        upgrade_text = "🏆 ماینر به ماکزیمم لول رسیده!"
    if level > 0:
        claim_label = f"⛏ جمع‌آوری ({format_coins(pending)} 🪙)" if pending > 0 else "⛏ جمع‌آوری (هنوز چیزی نشده)"
        keyboard.append([InlineKeyboardButton(claim_label, callback_data="miner_claim")])
    keyboard.append([InlineKeyboardButton("🔙 برگشت", callback_data="main_menu")])
    text = (
        f"⛏ *ماینر کوین*\n\n"
        f"لول فعلی: *{level}* / {MAX_MINER_LEVEL}\n"
        f"💵 درآمد ساعتی: *{format_coins(hourly)}* کوین\n"
        f"🕐 انباشته شده: *{format_coins(pending)}* کوین\n"
        f"💰 موجودی: {format_coins(user['coins'])} کوین\n\n"
        f"{upgrade_text}"
    )
    if edit:
        await msg_or_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await msg_or_query.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def mine_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = load_data()
    user = get_user(user_id, data)
    if not user["registered"]:
        await update.message.reply_text("❌ اول /start بزن!")
        return
    await do_mine(update.message, user, user_id, data)

async def do_mine(msg, user, user_id, data):
    if user["miner_level"] == 0:
        await msg.reply_text("❌ اول باید ماینر بخری! بنویس *ماینر*", parse_mode="Markdown")
        return
    pending = miner_pending_coins(user)
    if pending == 0:
        hourly = miner_hourly_income(user["miner_level"])
        await msg.reply_text(
            f"⛏ ماینر لول {user['miner_level']}\n\n"
            f"هنوز کوینی انباشته نشده!\n"
            f"درآمد ساعتی: {format_coins(hourly)} کوین\n"
            f"یه ساعت صبر کن بعد دوباره امتحان کن 😊"
        )
        return
    user["coins"] += pending
    user["miner_last_claim"] = time.time()
    if user["coins"] > user.get("max_coins", 0):
        user["max_coins"] = user["coins"]
    data[user_id] = user
    save_data(data)
    hourly = miner_hourly_income(user["miner_level"])
    await msg.reply_text(
        f"⛏ ماینر لول {user['miner_level']} جمع‌آوری شد!\n\n"
        f"💰 +{format_coins(pending)} کوین دریافت کردی!\n"
        f"📈 درآمد ساعتی: {format_coins(hourly)} کوین\n"
        f"موجودی جدید: {format_coins(user['coins'])} کوین"
    )

# ==================== سریال ماینر ====================
async def handle_serial_creation(msg, user, user_id, data, count, coin_per_serial):
    total_cost = count * coin_per_serial

    if user["coins"] < total_cost:
        await msg.reply_text(
            f"❌ کوین کافی نداری!\n"
            f"💰 موجودیت: {format_coins(user['coins'])}\n"
            f"💵 هزینه کل: {format_coins(total_cost)} ({count} سریال × {format_coins(coin_per_serial)})\n\n"
            f"کوین بیشتری جمع کن! 😊"
        )
        return

    await msg.reply_text(
        f"📩 لطفاً داخل پیوی ربات دستور ساخت سریال رو بدید!\n\n"
        f"🤖 ربات رو استارت کنید و همین پیام رو اونجا بفرستید:\n"
        f"`ساخت سریال ماینر {count} عدد {format_coins(coin_per_serial)}`",
        parse_mode="Markdown"
    )

async def handle_serial_creation_private(msg, user, user_id, data, count, coin_per_serial):
    total_cost = count * coin_per_serial

    if user["coins"] < total_cost:
        await msg.reply_text(
            f"❌ کوین کافی نداری!\n"
            f"💰 موجودیت: {format_coins(user['coins'])}\n"
            f"💵 هزینه کل: {format_coins(total_cost)}\n"
        )
        return

    serials = load_serials()
    user["coins"] -= total_cost
    if user["coins"] < user.get("max_coins", 0):
        pass
    data[user_id] = user
    save_data(data)

    generated = []
    for _ in range(count):
        while True:
            s = generate_serial()
            if s not in serials:
                serials[s] = {"coin": coin_per_serial, "used": False, "owner": user_id}
                generated.append(s)
                break

    save_serials(serials)

    lines = [
        f"✅ *{count} سریال ماینر ساخته شد!*\n"
        f"💰 از موجودیت {format_coins(total_cost)} کم شد\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🎁 *سریال‌ها:*\n"
    ]
    for s in generated:
        lines.append(f"`{s}` ← {format_coins(coin_per_serial)} کوین")
    lines.append(f"\n━━━━━━━━━━━━━━━")
    lines.append(f"💡 هر سریال فقط یک‌بار قابل استفاده‌ست!")

    await msg.reply_text("\n".join(lines), parse_mode="Markdown")

async def redeem_serial_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    args = context.args
    if not args:
        await update.message.reply_text(
            "📌 راهنما:\n/serial کد_۱۱_رقمی\n\nمثال: /serial 12345678901"
        )
        return
    serial_code = args[0].strip()
    data = load_data()
    user = get_user(user_id, data)
    if not user["registered"]:
        await update.message.reply_text("❌ اول /start بزن!")
        return
    serials = load_serials()
    if serial_code not in serials:
        await update.message.reply_text("❌ این سریال وجود نداره!")
        return
    serial_data = serials[serial_code]
    if serial_data.get("used"):
        await update.message.reply_text("❌ این سریال قبلاً استفاده شده!")
        return
    coin = serial_data["coin"]
    user["coins"] += coin
    if user["coins"] > user.get("max_coins", 0):
        user["max_coins"] = user["coins"]
    data[user_id] = user
    save_data(data)
    serials[serial_code]["used"] = True
    serials[serial_code]["used_by"] = user_id
    save_serials(serials)
    await update.message.reply_text(
        f"🎉 سریال با موفقیت استفاده شد!\n\n"
        f"💰 +{format_coins(coin)} کوین به حسابت اضافه شد!\n"
        f"موجودی جدید: {format_coins(user['coins'])} کوین"
    )

# ==================== گیفت ====================
async def gift_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "📌 راهنمای /gift:\n"
            "/gift مقدار آیدی\n\n"
            "مثال‌ها:\n"
            "• /gift 500کا 987654321\n"
            "• /gift 2میل 987654321\n"
            "• /gift 1بیل 987654321"
        )
        return
    amount_str = args[0]
    target_id = args[1]
    amount = parse_amount(amount_str)
    if amount <= 0:
        await update.message.reply_text("❌ مقدار اشتباهه! مثال: 500کا یا 2میل")
        return
    data = load_data()
    sender = get_user(user_id, data)
    if not sender["registered"]:
        await update.message.reply_text("❌ اول /start بزن!")
        return
    if target_id == user_id:
        await update.message.reply_text("❌ نمیتونی به خودت گیفت بدی!")
        return
    if target_id not in data or not data[target_id].get("registered"):
        await update.message.reply_text("❌ کاربر مقصد پیدا نشد.")
        return
    if sender["coins"] < amount:
        await update.message.reply_text(
            f"❌ کوین کافی نداری!\n"
            f"موجودی: {format_coins(sender['coins'])}\n"
            f"لازم: {format_coins(amount)}"
        )
        return
    sender["coins"] -= amount
    data[target_id]["coins"] += amount
    if data[target_id]["coins"] > data[target_id].get("max_coins", 0):
        data[target_id]["max_coins"] = data[target_id]["coins"]
    save_data(data)
    await update.message.reply_text(
        f"🎁 گیفت ارسال شد!\n\n"
        f"💰 {format_coins(amount)} کوین به {target_id} منتقل شد.\n"
        f"موجودی جدید: {format_coins(sender['coins'])} کوین"
    )
    try:
        await context.bot.send_message(
            chat_id=int(target_id),
            text=f"🎁 یه گیفت دریافت کردی!\n\n"
                 f"💰 {format_coins(amount)} کوین به حسابت اضافه شد!"
        )
    except:
        pass

async def mgift_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "📌 راهنمای /mgift:\n"
            "/mgift لول آیدی\n\n"
            "مثال: /mgift 10 987654321"
        )
        return
    try:
        levels = int(args[0])
    except:
        await update.message.reply_text("❌ لول باید عدد باشه!")
        return
    target_id = args[1]
    if levels <= 0:
        await update.message.reply_text("❌ لول باید بیشتر از صفر باشه!")
        return
    data = load_data()
    sender = get_user(user_id, data)
    if not sender["registered"]:
        await update.message.reply_text("❌ اول /start بزن!")
        return
    if target_id == user_id:
        await update.message.reply_text("❌ نمیتونی به خودت گیفت بدی!")
        return
    if target_id not in data or not data[target_id].get("registered"):
        await update.message.reply_text("❌ کاربر مقصد پیدا نشد.")
        return
    if sender["miner_level"] < levels:
        await update.message.reply_text(
            f"❌ لول ماینر کافی نداری!\n"
            f"لول فعلی: {sender['miner_level']}\n"
            f"لول لازم: {levels}"
        )
        return
    sender["miner_level"] -= levels
    data[target_id]["miner_level"] = data[target_id].get("miner_level", 0) + levels
    save_data(data)
    await update.message.reply_text(
        f"🎁 گیفت ماینر ارسال شد!\n\n"
        f"⛏ {levels} لول ماینر به {target_id} منتقل شد.\n"
        f"لول ماینر جدید شما: {sender['miner_level']}"
    )
    try:
        await context.bot.send_message(
            chat_id=int(target_id),
            text=f"🎁 یه گیفت ماینر دریافت کردی!\n\n"
                 f"⛏ {levels} لول ماینر به حسابت اضافه شد!\n"
                 f"لول جدید ماینرت: {data[target_id]['miner_level']}"
        )
    except:
        pass

# ==================== چلنج تاس ====================
async def handle_challenge_create(msg, user, user_id, data, amount, chat_id):
    if user["coins"] < amount:
        await msg.reply_text(
            f"❌ کوین کافی نداری!\n"
            f"💰 موجودیت: {format_coins(user['coins'])}\n"
            f"💵 شرط: {format_coins(amount)}"
        )
        return

    challenges = load_challenges()
    chat_key = str(chat_id)

    # بررسی چلنج فعال
    if chat_key in challenges and challenges[chat_key].get("status") == "waiting":
        await msg.reply_text(
            "❌ یه چلنج فعال الان تو این گروه هست!\n"
            "صبر کن اون تموم بشه 😊"
        )
        return

    user["coins"] -= amount
    data[user_id] = user
    save_data(data)

    challenges[chat_key] = {
        "creator_id": user_id,
        "creator_name": user.get("username") or f"کاربر {user_id[-4:]}",
        "amount": amount,
        "status": "waiting",
        "created_at": time.time()
    }
    save_challenges(challenges)

    creator_name = f"@{user.get('username')}" if user.get("username") else f"کاربر {user_id[-4:]}"
    await msg.reply_text(
        f"🏆 *چلنج تاس ایجاد شد!*\n\n"
        f"👤 چلنج‌دهنده: {creator_name}\n"
        f"💰 مبلغ شرط: *{format_coins(amount)}* کوین\n\n"
        f"🎯 برای پذیرش بنویس:\n"
        f"*قبول میکنم چلنجتو*\n\n"
        f"⏰ چلنج تا ۱۰ دقیقه معتبره!",
        parse_mode="Markdown"
    )

async def handle_challenge_accept(msg, user, user_id, data, chat_id):
    challenges = load_challenges()
    chat_key = str(chat_id)

    if chat_key not in challenges or challenges[chat_key].get("status") != "waiting":
        await msg.reply_text("❌ الان هیچ چلنج فعالی تو این گروه نیست!")
        return

    challenge = challenges[chat_key]

    if challenge["creator_id"] == user_id:
        await msg.reply_text("❌ نمیتونی چلنج خودتو قبول کنی!")
        return

    # بررسی انقضا (۱۰ دقیقه)
    if time.time() - challenge["created_at"] > 600:
        # برگرداندن پول به ایجادکننده
        data_temp = load_data()
        if challenge["creator_id"] in data_temp:
            data_temp[challenge["creator_id"]]["coins"] += challenge["amount"]
            save_data(data_temp)
        del challenges[chat_key]
        save_challenges(challenges)
        await msg.reply_text("⏰ چلنج منقضی شد و پول به ایجادکننده برگشت!")
        return

    amount = challenge["amount"]
    if user["coins"] < amount:
        await msg.reply_text(
            f"❌ کوین کافی نداری!\n"
            f"💰 موجودیت: {format_coins(user['coins'])}\n"
            f"💵 شرط: {format_coins(amount)}"
        )
        return

    user["coins"] -= amount
    data[user_id] = user
    save_data(data)

    challenges[chat_key]["challenger_id"] = user_id
    challenges[chat_key]["challenger_name"] = user.get("username") or f"کاربر {user_id[-4:]}"
    challenges[chat_key]["status"] = "accepted"
    save_challenges(challenges)

    creator_name = f"@{challenge['creator_name']}" if not challenge['creator_name'].startswith('کاربر') else challenge['creator_name']
    challenger_name = f"@{user.get('username')}" if user.get("username") else f"کاربر {user_id[-4:]}"

    await msg.reply_text(
        f"✅ *چلنج پذیرفته شد!*\n\n"
        f"👤 چلنج‌دهنده: {creator_name}\n"
        f"🆚 حریف: {challenger_name}\n"
        f"💰 شرط: *{format_coins(amount)}* کوین هر نفر\n"
        f"🏆 برنده: *{format_coins(amount * 2)}* کوین می‌بره!\n\n"
        f"🎲 {creator_name} بنویس *شروع* تا تاس‌ها پرتاب بشن!",
        parse_mode="Markdown"
    )

async def handle_challenge_start(msg, user, user_id, data, chat_id):
    challenges = load_challenges()
    chat_key = str(chat_id)

    if chat_key not in challenges or challenges[chat_key].get("status") != "accepted":
        await msg.reply_text("❌ هیچ چلنج پذیرفته‌شده‌ای الان نیست!")
        return

    challenge = challenges[chat_key]

    if challenge["creator_id"] != user_id:
        await msg.reply_text("❌ فقط ایجادکننده چلنج می‌تونه تاس بندازه!")
        return

    # پرتاب تاس برای هر دو نفر
    c_d1 = random.randint(1, 6)
    c_d2 = random.randint(1, 6)
    ch_d1 = random.randint(1, 6)
    ch_d2 = random.randint(1, 6)

    c_total = c_d1 + c_d2
    ch_total = ch_d1 + ch_d2

    amount = challenge["amount"]
    creator_id = challenge["creator_id"]
    challenger_id = challenge["challenger_id"]
    creator_name = challenge.get("creator_name", "")
    challenger_name = challenge.get("challenger_name", "")

    c_display = f"@{creator_name}" if creator_name and not creator_name.startswith('کاربر') else creator_name
    ch_display = f"@{challenger_name}" if challenger_name and not challenger_name.startswith('کاربر') else challenger_name

    dice_faces = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣"}

    result_text = (
        f"🎲 *نتیجه چلنج تاس!*\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"👤 {c_display}:\n"
        f"  {dice_faces[c_d1]} + {dice_faces[c_d2]} = *{c_total}*\n\n"
        f"🆚\n\n"
        f"👤 {ch_display}:\n"
        f"  {dice_faces[ch_d1]} + {dice_faces[ch_d2]} = *{ch_total}*\n\n"
        f"━━━━━━━━━━━━━━━\n"
    )

    data_reload = load_data()

    if c_total > ch_total:
        # ایجادکننده برنده
        winner_id = creator_id
        winner_name = c_display
        loser_name = ch_display
        prize = amount * 2
        if winner_id in data_reload:
            data_reload[winner_id]["coins"] += prize
            if data_reload[winner_id]["coins"] > data_reload[winner_id].get("max_coins", 0):
                data_reload[winner_id]["max_coins"] = data_reload[winner_id]["coins"]
        result_text += f"🏆 *برنده: {winner_name}!*\n💰 +{format_coins(prize)} کوین!"
    elif ch_total > c_total:
        # حریف برنده
        winner_id = challenger_id
        winner_name = ch_display
        loser_name = c_display
        prize = amount * 2
        if winner_id in data_reload:
            data_reload[winner_id]["coins"] += prize
            if data_reload[winner_id]["coins"] > data_reload[winner_id].get("max_coins", 0):
                data_reload[winner_id]["max_coins"] = data_reload[winner_id]["coins"]
        result_text += f"🏆 *برنده: {winner_name}!*\n💰 +{format_coins(prize)} کوین!"
    else:
        # مساوی - برگشت پول
        if creator_id in data_reload:
            data_reload[creator_id]["coins"] += amount
        if challenger_id in data_reload:
            data_reload[challenger_id]["coins"] += amount
        result_text += f"🤝 *مساوی!* پول هر دو نفر برگشت!"

    save_data(data_reload)
    del challenges[chat_key]
    save_challenges(challenges)

    await msg.reply_text(result_text, parse_mode="Markdown")

# ==================== مدیریت پیام‌ها ====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    is_owner = int(user_id) == BOT_OWNER_ID
    data = load_data()
    user = get_user(user_id, data)

    # ===== مدیریت گروه با دستور به ربی =====
    if chat_type in ["group", "supergroup"]:
        admin_cmd = detect_admin_group_command(text, user_id)
        if admin_cmd and update.message.reply_to_message:
            if admin_cmd == "restrict":
                await restrict_member(update, context)
                return
            elif admin_cmd == "ban":
                await ban_member(update, context)
                return
            elif admin_cmd == "unban":
                await unban_member(update, context)
                return

        # ربی صدا زده شده؟
        if is_bot_called(text):
            if is_owner:
                # مالک: جونم
                owner_replies = [
                    "جونم؟ 💕",
                    "جانم مالکم! 😊💕",
                    "بله قربان! 😄",
                    "جونم چی شد؟ 💕",
                ]
                await update.message.reply_text(random.choice(owner_replies))
            else:
                # عضو عادی: بفرمایید
                member_replies = [
                    "بفرمایید؟ 😊",
                    "بله؟ در خدمتم 🙏",
                    "بفرما؟ 😄",
                    "جانم؟ چطور میتونم کمک کنم؟ 😊",
                ]
                # اگه پیام اضافه‌ای داشت، جواب هوشمند بده
                clean = text
                for t in BOT_NAME_TRIGGERS:
                    clean = clean.replace(t, "").strip()
                if clean:
                    response = get_robi_response(clean)
                    await update.message.reply_text(response)
                else:
                    await update.message.reply_text(random.choice(member_replies))
            return

        # اگه ریپلای به ربات بود
        if (update.message.reply_to_message and
                update.message.reply_to_message.from_user and
                update.message.reply_to_message.from_user.is_bot):
            if is_owner:
                owner_replies = ["جونم؟ 💕", "جانم! 😊", "بله قربان؟ 💕"]
                await update.message.reply_text(random.choice(owner_replies))
            else:
                response = get_robi_response(text)
                await update.message.reply_text(response)
            return

        # در گروه بقیه دستورات رو هم چک کن
        if not user["registered"]:
            return

    # ===== دستورات متنی (پیوی و گروه) =====
    if not user["registered"]:
        if any(g in text for g in ["سلام", "هی", "درود", "hi", "hello"]):
            await update.message.reply_text(random.choice(GREETING_RESPONSES))
        return

    if text in ["موجودی", "بالانس", "balance"]:
        await show_balance(update.message, update.effective_user)
        return

    if text in ["پروفیت", "profit"]:
        await show_profit(update.message, update.effective_user)
        return

    if text in ["گردونه", "wheel", "چرخونه"]:
        await show_wheel(update.message, user, edit=False)
        return

    if text in ["ماینر", "miner", "mine"]:
        await show_miner(update.message, user, user_id, edit=False)
        return

    if text in ["منو", "menu", "خانه", "home"]:
        await show_main_menu_msg(update.message, user, user_id, is_admin(user_id))
        return

    if text in ["تاس", "dice"]:
        await show_dice_menu(update.message, user)
        return

    if text in ["جمع‌آوری", "جمع آوری", "برداشت", "claim"]:
        await do_mine(update.message, user, user_id, data)
        return

    if text in ["پولداران", "ثروتمندان", "لیدربورد", "leaderboard"]:
        await show_leaderboard(update.message)
        return

    # ===== سریال ماینر =====
    if "ساخت سریال ماینر" in text:
        result = detect_serial_command(text)
        if result:
            count, coin_per_serial = result
            if chat_type == "private":
                await handle_serial_creation_private(update.message, user, user_id, data, count, coin_per_serial)
            else:
                await handle_serial_creation(update.message, user, user_id, data, count, coin_per_serial)
        else:
            await update.message.reply_text(
                "❌ فرمت اشتباهه!\n\n"
                "✅ فرمت صحیح:\n"
                "ساخت سریال ماینر [تعداد] عدد [مقدار]\n\n"
                "مثال:\n"
                "• ساخت سریال ماینر ۵ عدد ۱۰کا\n"
                "• ساخت سریال ماینر ۳ عدد ۱میل"
            )
        return

    # ===== چلنج تاس =====
    if "چلنج تاس" in text:
        amount = detect_challenge_command(text)
        if amount:
            await handle_challenge_create(update.message, user, user_id, data, amount, chat_id)
        else:
            await update.message.reply_text(
                "❌ فرمت اشتباهه!\n\n"
                "✅ فرمت صحیح:\n"
                "چلنج تاس [مقدار]\n\n"
                "مثال:\n"
                "• چلنج تاس ۱۰میل\n"
                "• چلنج تاس ۵۰۰کا"
            )
        return

    if "قبول میکنم چلنجتو" in text or "قبول میکنم چلنجت" in text:
        await handle_challenge_accept(update.message, user, user_id, data, chat_id)
        return

    if text.strip() == "شروع":
        await handle_challenge_start(update.message, user, user_id, data, chat_id)
        return

    # ===== شرط‌بندی زوج/فرد =====
    bet = detect_bet_command(text)
    if bet:
        game_type, amount, choice = bet
        await play_zojfard(update.message, user, user_id, data, amount, choice)
        return

    # ===== سلام (پیوی) =====
    if chat_type == "private":
        if any(g in text for g in ["سلام", "هی", "درود", "hi", "hello"]):
            await update.message.reply_text(random.choice(GREETING_RESPONSES))
        return

# ==================== زوج/فرد ====================
async def play_zojfard(msg, user, user_id, data, amount, choice):
    if user["coins"] < amount:
        await msg.reply_text(
            f"❌ کوین کافی نداری!\n"
            f"💰 موجودیت: {format_coins(user['coins'])}\n"
            f"💵 شرط: {format_coins(amount)}"
        )
        return
    roll = random.randint(1, 100)
    is_even = (roll % 2 == 0)
    result_fa = "زوج" if is_even else "فرد"
    choice_fa = "زوج" if choice == "zoj" else "فرد"
    won = (choice == "zoj" and is_even) or (choice == "fard" and not is_even)
    if won:
        user["coins"] += amount
        emoji = "🎉"
        result_msg = f"بردی! +{format_coins(amount)} کوین"
    else:
        user["coins"] -= amount
        emoji = "😢"
        result_msg = f"باختی! -{format_coins(amount)} کوین"
    if user["coins"] > user.get("max_coins", 0):
        user["max_coins"] = user["coins"]
    data[user_id] = user
    save_data(data)
    await msg.reply_text(
        f"{emoji} *زوج و فرد*\n\n"
        f"🎲 عدد: *{roll}* ({result_fa})\n"
        f"🎯 انتخاب تو: {choice_fa}\n\n"
        f"{'✅' if won else '❌'} {result_msg}\n"
        f"💰 موجودی: {format_coins(user['coins'])} کوین",
        parse_mode="Markdown"
    )

# ==================== تاس ====================
async def show_dice_menu(msg, user):
    keyboard = []
    for mult in DICE_MULTIPLIERS:
        keyboard.append([InlineKeyboardButton(
            f"🎲 ضریب x{mult}",
            callback_data=f"dice_mult_{mult}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 برگشت", callback_data="main_menu")])
    await msg.reply_text(
        f"🎰 *بازی تاس*\n\n"
        f"💰 موجودی: {format_coins(user['coins'])} کوین\n\n"
        f"یه عدد تصادفی ۱-۱۰۰ داده میشه\n"
        f"اگه عددت از ۵۰ بیشتر بود، به ضریب انتخابی می‌بری!\n\n"
        f"ضریب رو انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ==================== کالبک‌ها ====================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    data = load_data()
    user = get_user(user_id, data)

    if not user["registered"]:
        await query.edit_message_text("❌ اول /start بزن!")
        return

    cb = query.data

    if cb == "main_menu":
        await show_main_menu_msg(query, user, user_id, is_admin(user_id), edit=True)

    elif cb == "balance":
        username = user.get("username", "") or query.from_user.username or ""
        id_display = f"@{username}" if username else f"#{user_id}"
        await query.edit_message_text(
            f"👤 *اطلاعات کاربر*\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🆔 کاربر عزیز با آیدی {id_display}\n\n"
            f"💰 موجودی شما: *{format_coins(user['coins'])}* کوین\n"
            f"⛏ لول ماینر شما: *{user['miner_level']}*\n"
            f"🏆 رکورد بیشترین موجودی: *{format_coins(user['max_coins'])}* کوین\n"
            f"━━━━━━━━━━━━━━━",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 برگشت", callback_data="main_menu")]])
        )

    elif cb == "profit":
        level = user["miner_level"]
        hourly = miner_hourly_income(level)
        pending = miner_pending_coins(user)
        if level < MAX_MINER_LEVEL:
            next_cost = miner_upgrade_cost(level)
            next_hourly = miner_hourly_income(level + 1)
            next_info = (
                f"⬆️ پروفیت لول {level+1}: *{format_coins(next_hourly)}* در ساعت\n"
                f"💵 هزینه ارتقا: *{format_coins(next_cost)}* کوین"
            )
        else:
            next_info = "🏆 ماینر به ماکزیمم لول رسیده!"
        await query.edit_message_text(
            f"📈 *پروفیت شما*\n━━━━━━━━━━━━━━━\n\n"
            f"⛏ لول ماینر: *{level}*\n"
            f"⏱ درآمد ساعتی: *{format_coins(hourly)}* کوین\n"
            f"🕐 انباشته شده: *{format_coins(pending)}* کوین\n\n"
            f"{next_info}\n━━━━━━━━━━━━━━━",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 برگشت", callback_data="main_menu")]])
        )

    elif cb == "leaderboard":
        data_all = load_data()
        registered = [
            (uid, u) for uid, u in data_all.items()
            if u.get("registered") and u.get("coins", 0) > 0
        ]
        top10 = sorted(registered, key=lambda x: x[1].get("coins", 0), reverse=True)[:10]
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        lines = ["🏆 *ثروتمندترین‌های ربات*\n━━━━━━━━━━━━━━━\n"]
        for i, (uid, u) in enumerate(top10):
            username = u.get("username", "")
            name = f"@{username}" if username else f"کاربر {uid[-4:]}"
            coins = format_coins(u.get("coins", 0))
            lines.append(f"{medals[i]} {name}: *{coins}* کوین")
        if not top10:
            lines.append("هنوز کسی ثبت‌نام نکرده!")
        lines.append("\n━━━━━━━━━━━━━━━")
        await query.edit_message_text(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 برگشت", callback_data="main_menu")]])
        )

    elif cb == "game_zojfard":
        keyboard = [
            [
                InlineKeyboardButton("زوج 🔵", callback_data="zf_choose_zoj"),
                InlineKeyboardButton("فرد 🔴", callback_data="zf_choose_fard"),
            ],
            [InlineKeyboardButton("🔙 برگشت", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"🎲 *زوج و فرد*\n\n"
            f"💰 موجودی: {format_coins(user['coins'])} کوین\n\n"
            f"انتخاب کن:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif cb in ["zf_choose_zoj", "zf_choose_fard"]:
        choice = "zoj" if cb == "zf_choose_zoj" else "fard"
        choice_fa = "زوج" if choice == "zoj" else "فرد"
        amounts = [1000, 5000, 10000, 50000, 100000, 500000, 1000000]
        keyboard = []
        row = []
        for a in amounts:
            if user["coins"] >= a:
                row.append(InlineKeyboardButton(
                    format_coins(a), callback_data=f"zf_bet_{choice}_{a}"
                ))
                if len(row) == 3:
                    keyboard.append(row)
                    row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔙 برگشت", callback_data="game_zojfard")])
        await query.edit_message_text(
            f"🎯 انتخاب تو: *{choice_fa}*\n\n"
            f"💰 موجودی: {format_coins(user['coins'])} کوین\n\n"
            f"مقدار شرط رو انتخاب کن:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif cb.startswith("zf_bet_"):
        parts = cb.split("_")
        choice = parts[2]
        amount = int(parts[3])
        await play_zojfard_inline(query, user, user_id, data, amount, choice)

    elif cb == "game_dice":
        keyboard = []
        for mult in DICE_MULTIPLIERS:
            keyboard.append([InlineKeyboardButton(
                f"🎲 ضریب x{mult}",
                callback_data=f"dice_mult_{mult}"
            )])
        keyboard.append([InlineKeyboardButton("🔙 برگشت", callback_data="main_menu")])
        await query.edit_message_text(
            f"🎰 *بازی تاس*\n\n"
            f"💰 موجودی: {format_coins(user['coins'])} کوین\n\n"
            f"اگه عددت از ۵۰ بیشتر بود، به ضریب انتخابی می‌بری!\n\n"
            f"ضریب رو انتخاب کن:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif cb.startswith("dice_mult_"):
        mult = int(cb.split("_")[-1])
        amounts = [1000, 5000, 10000, 50000, 100000, 500000, 1000000]
        keyboard = []
        row = []
        for a in amounts:
            if user["coins"] >= a:
                row.append(InlineKeyboardButton(
                    format_coins(a), callback_data=f"dice_play_{mult}_{a}"
                ))
                if len(row) == 3:
                    keyboard.append(row)
                    row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔙 برگشت", callback_data="game_dice")])
        await query.edit_message_text(
            f"🎰 ضریب x{mult} انتخاب شد!\n\n"
            f"💰 موجودی: {format_coins(user['coins'])} کوین\n\n"
            f"مقدار شرط:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif cb.startswith("dice_play_"):
        parts = cb.split("_")
        mult = int(parts[2])
        amount = int(parts[3])
        await play_dice(query, user, user_id, data, amount, mult)

    elif cb == "game_wheel":
        await show_wheel(query, user, edit=True)

    elif cb == "wheel_spin":
        can, wait_secs = can_spin_wheel(user)
        if not can:
            await query.edit_message_text(
                f"⏳ باید صبر کنی!\nتا چرخش بعدی: {seconds_to_persian(wait_secs)}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 برگشت", callback_data="main_menu")]])
            )
            return
        d1, d2, d3, prize, label, triple = spin_wheel()
        user["coins"] += prize
        user["wheel_last_spin"] = time.time()
        if user["coins"] > user.get("max_coins", 0):
            user["max_coins"] = user["coins"]
        data[user_id] = user
        save_data(data)
        dice_faces = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣"}
        triple_text = "\n🔥 سه‌تایی! جایزه ۳ برابر شد!" if triple else ""
        await query.edit_message_text(
            f"🎡 *گردونه شانس*\n\n"
            f"🎲 {dice_faces[d1]} {dice_faces[d2]} {dice_faces[d3]}{triple_text}\n\n"
            f"🎁 جایزه: {label}\n"
            f"💰 +{format_coins(prize)} کوین!\n\n"
            f"موجودی جدید: {format_coins(user['coins'])} کوین",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 منو", callback_data="main_menu")]])
        )

    elif cb == "miner_menu":
        await show_miner(query, user, user_id, edit=True)

    elif cb == "miner_upgrade":
        level = user["miner_level"]
        if level >= MAX_MINER_LEVEL:
            await query.answer("ماینر به ماکزیمم رسیده!", show_alert=True)
            return
        cost = miner_upgrade_cost(level)
        if user["coins"] < cost:
            await query.answer(f"کوین کافی نداری! لازم: {format_coins(cost)}", show_alert=True)
            return
        user["coins"] -= cost
        user["miner_level"] += 1
        if user["miner_last_claim"] == 0:
            user["miner_last_claim"] = time.time()
        data[user_id] = user
        save_data(data)
        await show_miner(query, user, user_id, edit=True)

    elif cb == "miner_claim":
        pending = miner_pending_coins(user)
        if pending == 0:
            await query.answer("هنوز کوینی انباشته نشده!", show_alert=True)
            return
        user["coins"] += pending
        user["miner_last_claim"] = time.time()
        if user["coins"] > user.get("max_coins", 0):
            user["max_coins"] = user["coins"]
        data[user_id] = user
        save_data(data)
        await show_miner(query, user, user_id, edit=True)

async def play_zojfard_inline(query, user, user_id, data, amount, choice):
    if user["coins"] < amount:
        await query.answer("کوین کافی نداری!", show_alert=True)
        return
    roll = random.randint(1, 100)
    is_even = (roll % 2 == 0)
    result_fa = "زوج" if is_even else "فرد"
    choice_fa = "زوج" if choice == "zoj" else "فرد"
    won = (choice == "zoj" and is_even) or (choice == "fard" and not is_even)
    if won:
        user["coins"] += amount
        emoji = "🎉"
        result_msg = f"بردی! +{format_coins(amount)} کوین"
    else:
        user["coins"] -= amount
        emoji = "😢"
        result_msg = f"باختی! -{format_coins(amount)} کوین"
    if user["coins"] > user.get("max_coins", 0):
        user["max_coins"] = user["coins"]
    data[user_id] = user
    save_data(data)
    keyboard = [
        [
            InlineKeyboardButton("🔄 دوباره", callback_data="game_zojfard"),
            InlineKeyboardButton("🔙 منو", callback_data="main_menu"),
        ]
    ]
    await query.edit_message_text(
        f"{emoji} *زوج و فرد*\n\n"
        f"🎲 عدد: *{roll}* ({result_fa})\n"
        f"🎯 انتخاب تو: {choice_fa}\n\n"
        f"{'✅' if won else '❌'} {result_msg}\n"
        f"💰 موجودی: {format_coins(user['coins'])} کوین",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def play_dice(query, user, user_id, data, amount, mult):
    if user["coins"] < amount:
        await query.answer("کوین کافی نداری!", show_alert=True)
        return
    roll = random.randint(1, 100)
    won = roll > 50
    if won:
        gain = amount * mult
        user["coins"] += gain
        emoji = "🎉"
        result_msg = f"بردی! +{format_coins(gain)} کوین"
    else:
        user["coins"] -= amount
        emoji = "😢"
        result_msg = f"باختی! -{format_coins(amount)} کوین"
    if user["coins"] > user.get("max_coins", 0):
        user["max_coins"] = user["coins"]
    data[user_id] = user
    save_data(data)
    keyboard = [
        [
            InlineKeyboardButton("🔄 دوباره", callback_data=f"dice_mult_{mult}"),
            InlineKeyboardButton("🔙 منو", callback_data="main_menu"),
        ]
    ]
    await query.edit_message_text(
        f"🎰 *تاس - ضریب x{mult}*\n\n"
        f"🎲 عدد: *{roll}* {'(بالای ۵۰ ✅)' if won else '(زیر ۵۰ ❌)'}\n\n"
        f"{emoji} {result_msg}\n"
        f"💰 موجودی: {format_coins(user['coins'])} کوین",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================== پاسخ‌های مکالمه ربی ====================
ROBI_RESPONSES = {
    "سلام": ["سلام عزیزم! 😊", "سلام سلام! 👋", "درود! چطوری؟ 😄"],
    "حالت": ["ممنون خوبم! تو چطوری؟ 😊", "عالیم! مرسی که پرسیدی 🌸"],
    "چطوری": ["ممنون خوبم! تو چطوری؟ 😊", "عالیم! چه خبر؟ 😄"],
    "خوبی": ["آره ممنون! تو خوبی؟ 😊", "عالیم مرسی 🌸"],
    "ممنون": ["خواهش میکنم! 🙏", "قابلی نداشت عزیزم 😊"],
    "مرسی": ["خواهش میکنم! 😊", "قابلت رو نداشت 🌸"],
    "چیکار": ["اینجام که کمک کنم! 😊", "در خدمتتم 🙏"],
    "بازی": ["میخوای بازی کنی؟ بنویس *منو* 🎮", "برو منو رو ببین، بازی‌های باحال داریم! 🎲"],
    "کمک": ["بنویس *منو* تا همه امکانات رو ببینی 😊", "چه کمکی از دستم برمیاد؟ 🙏"],
    "خداحافظ": ["خداحافظ! 👋 برگرد پیشم 😊", "بای بای! مواظب خودت باش 🌸"],
    "شب بخیر": ["شب بخیر! خواب خوب ببینی 🌙", "شب بخیر عزیزم 🌙✨"],
    "صبح بخیر": ["صبح بخیر! روز خوبی داشته باشی ☀️", "صبح بخیر! ☀️😊"],
}

def get_robi_response(text: str) -> str:
    text_lower = text.lower()
    for key, responses in ROBI_RESPONSES.items():
        if key in text_lower:
            return random.choice(responses)
    # پاسخ پیش‌فرض
    defaults = [
        "اینجام! 😊 چیزی لازم داری؟",
        "جانم؟ 😄",
        "بله؟ در خدمتم 🙏",
        "بفرما؟ 😊",
        "چطور میتونم کمک کنم؟ 🌸",
    ]
    return random.choice(defaults)

def is_bot_called(text: str) -> bool:
    text_lower = text.lower()
    for trigger in BOT_NAME_TRIGGERS:
        if trigger in text_lower:
            return True
    return False

# ==================== مدیریت گروه ====================
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """خوش‌آمدگویی به عضو جدید"""
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        name = member.full_name
        username = f"@{member.username}" if member.username else name
        uid = member.id
        await update.message.reply_text(
            f"👋 خوش اومدی به گپ ما {username}! ❤️\n"
            f"🆔 آیدی: `{uid}`\n\n"
            f"امیدوارم وقت خوبی داشته باشی 😊",
            parse_mode="Markdown"
        )

async def restrict_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """محدود کردن عضو با ریپلای + دستور به ربی"""
    if not update.message or not update.message.reply_to_message:
        await update.message.reply_text("❌ باید روی پیام کسی ریپلای کنی!")
        return
    user_id = str(update.effective_user.id)
    if int(user_id) != BOT_OWNER_ID:
        await update.message.reply_text("❌ فقط مالک ربات می‌تونه این کارو بکنه!")
        return
    target = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    try:
        from telegram import ChatPermissions
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target.id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
            )
        )
        name = f"@{target.username}" if target.username else target.full_name
        await update.message.reply_text(
            f"🔇 {name} محدود شد!\n"
            f"🆔 آیدی: `{target.id}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ نشد! مطمئن شو ربات ادمین گروهه.\nخطا: {e}")

async def ban_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف عضو با ریپلای + دستور به ربی"""
    if not update.message or not update.message.reply_to_message:
        await update.message.reply_text("❌ باید روی پیام کسی ریپلای کنی!")
        return
    user_id = str(update.effective_user.id)
    if int(user_id) != BOT_OWNER_ID:
        await update.message.reply_text("❌ فقط مالک ربات می‌تونه این کارو بکنه!")
        return
    target = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    try:
        await context.bot.ban_chat_member(chat_id=chat_id, user_id=target.id)
        name = f"@{target.username}" if target.username else target.full_name
        await update.message.reply_text(
            f"🚫 {name} از گروه حذف شد!\n"
            f"🆔 آیدی: `{target.id}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ نشد! مطمئن شو ربات ادمین گروهه.\nخطا: {e}")

async def unban_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """آنبن کردن"""
    if not update.message or not update.message.reply_to_message:
        await update.message.reply_text("❌ باید روی پیام کسی ریپلای کنی!")
        return
    user_id = str(update.effective_user.id)
    if int(user_id) != BOT_OWNER_ID:
        await update.message.reply_text("❌ فقط مالک ربات می‌تونه این کارو بکنه!")
        return
    target = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    try:
        from telegram import ChatPermissions
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            )
        )
        name = f"@{target.username}" if target.username else target.full_name
        await update.message.reply_text(
            f"✅ {name} آزاد شد!\n"
            f"🆔 آیدی: `{target.id}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ خطا: {e}")

def detect_admin_group_command(text: str, user_id: str) -> str | None:
    """تشخیص دستورات مدیریتی که مالک به ربی میده"""
    if int(user_id) != BOT_OWNER_ID:
        return None
    text_lower = text.lower()
    # بررسی اینکه ربی صدا زده شده
    called = is_bot_called(text_lower)
    if not called:
        return None
    if any(w in text_lower for w in ["محدودش کن", "محدود کن", "ساکتش کن", "میوت کن", "mute"]):
        return "restrict"
    if any(w in text_lower for w in ["حذفش کن", "بنش کن", "اخراجش کن", "ban", "kick"]):
        return "ban"
    if any(w in text_lower for w in ["آزادش کن", "آنبنش کن", "unban", "رفع محدودیت"]):
        return "unban"
    return None

# ==================== اجرا ====================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(CommandHandler("profit", profit_cmd))
    app.add_handler(CommandHandler("wheel", wheel_cmd))
    app.add_handler(CommandHandler("miner", miner_cmd))
    app.add_handler(CommandHandler("mine", mine_cmd))
    app.add_handler(CommandHandler("gift", gift_cmd))
    app.add_handler(CommandHandler("mgift", mgift_cmd))
    app.add_handler(CommandHandler("serial", redeem_serial_cmd))
    app.add_handler(CommandHandler("leaderboard", leaderboard_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("ربات شروع به کار کرد!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
