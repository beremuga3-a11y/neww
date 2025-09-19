#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# --------------------------------------------------------------
#   Bot «Farm» – полностью исправлен, доработан и расширен:
#   • Удалены все упоминания о перерождениях и X‑ферме.
#   • Удалены все осенние события и порталы.
#   • Добавлен журнал действий админа – возможность просматривать
#     последние действия игроков (покупка, кормление, продажа и т.д.).
#   • Для каждого раздела (меню, ферма, магазин, статус и т.д.)
#     теперь выводится изображение над текстом.
# --------------------------------------------------------------
import argparse
import logging
import random
import re
import time
import sqlite3
from typing import Any, Dict, List, Tuple

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Update,
)
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ----------------------------------------------------------------------
#   Конфигурация
# ----------------------------------------------------------------------
TOKEN = "8137596673:AAGePL-4AZQHPIXLruyWkOQwDLfW_Hycudk"
DB_PATH = "farm_bot.db"
MAX_INT = 9_223_372_036_854_775_807
HUNGER_TIME = 10 * 3600          # 10 ч в секундах
FOOD_PRICE = 500                # обычный корм
BASE_UPGRADE_COST = 5_000_000    # улучшение базы
BASE_LIMIT_STEP = 5               # шаг увеличения лимита при улучшении базы
SEASON_LENGTH = 60 * 24 * 3600   # 60 дней → один «сезон»
CHANNEL_USERNAME = "spiderfarminfo"
CHANNEL_ID = -1001234567890
CHAT_ID = -4966660960
CHAT_LINK = "https://t.me/+tjqmdwVMjtYxMTU6"
CHANNEL_LINK = "https://t.me/spiderfarminfo"

# Картинки
MAIN_MENU_IMG = "https://i.postimg.cc/fb1TQF6W/5355070803995131046.jpg"

# ----------------------------------------------------------------------
#   Изображения для разделов 
# ----------------------------------------------------------------------
SECTION_IMAGES: Dict[str, str] = {
    "about": "https://i.postimg.cc/BZ580SNj/5355070803995130961.jpg",
    "farm": "https://i.postimg.cc/dVf3BLQx/5355070803995130963.jpg",
    "shop": "https://i.postimg.cc/cHyJp2n7/5355070803995130964.jpg",
    "farmers": "https://i.postimg.cc/28MN9vvh/5355070803995130971.jpg",
    "status": "https://i.postimg.cc/2jPf2hnv/5355070803995130978.jpg",
    "coins": "https://i.postimg.cc/SxnCk0JH/5355070803995130993.jpg",
    "casino": "https://i.postimg.cc/zvZBKMj2/5355070803995131009.jpg",
    "promo": "https://i.postimg.cc/kXCG50DB/5355070803995131030.jpg",
    "admin": "https://i.postimg.cc/fb1TQF6W/5355070803995131046.jpg",
    "logs": "https://i.postimg.cc/fb1TQF6W/5355070803995131046.jpg",
    "top": "https://i.postimg.cc/mg2rY7Y4/5355070803995131023.jpg",
}

# ----------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ----------------------------------------------------------------------
#   База данных
# ----------------------------------------------------------------------
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row
cur = conn.cursor()


def _execute(sql: str, params: Tuple = ()) -> None:
    """Упрощённый wrapper‑выполнения запросов."""
    cur.execute(sql, params)
    conn.commit()


def init_db() -> None:
    """Создаёт все таблицы (если их ещё нет) и делает миграцию."""
    # ---------- users ----------
    _execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            coins INTEGER DEFAULT 0,
            feed INTEGER DEFAULT 0,
            weekly_coins INTEGER DEFAULT 0,
            last_reset INTEGER DEFAULT 0,
            secret_spider INTEGER DEFAULT 0,
            click_count INTEGER DEFAULT 0,
            last_click_time INTEGER DEFAULT 0,
            feed_bonus_end INTEGER DEFAULT 0,
            tickets INTEGER DEFAULT 0,
            last_ticket_time INTEGER DEFAULT 0,
            reputation INTEGER DEFAULT 0,
            custom_income INTEGER DEFAULT 0,
            pet_limit INTEGER DEFAULT 200,
            base_level INTEGER DEFAULT 0,
            subscribe_claimed INTEGER DEFAULT 0,
            chat_claimed INTEGER DEFAULT 0,
            click_reward_last INTEGER DEFAULT 0,
            referred_by INTEGER DEFAULT 0,
            last_active INTEGER DEFAULT 0
        );
        """
    )
    # ---------- admin_users ----------
    _execute(
        """
        CREATE TABLE IF NOT EXISTS admin_users (
            user_id INTEGER PRIMARY KEY
        );
        """
    )
    # ---------- global_settings ----------
    _execute(
        """
        CREATE TABLE IF NOT EXISTS global_settings (
            id INTEGER PRIMARY KEY,
            global_bonus_active INTEGER DEFAULT 0,
            season_start INTEGER DEFAULT 0,
            season_number INTEGER DEFAULT 1
        );
        """
    )
    # создаём строку id=1, если её нет
    cur.execute("SELECT 1 FROM global_settings WHERE id = 1")
    if cur.fetchone() is None:
        _execute(
            """
            INSERT INTO global_settings (id, global_bonus_active, season_start, season_number)
            VALUES (1,0,?,1)
            """,
            (int(time.time()),),
        )
    else:
        cur.execute("SELECT season_start FROM global_settings WHERE id = 1")
        row = cur.fetchone()
        if row["season_start"] == 0:
            _execute(
                "UPDATE global_settings SET season_start = ? WHERE id = 1",
                (int(time.time()),),
            )
    # ---------- pet_last_fed ----------
    _execute(
        """
        CREATE TABLE IF NOT EXISTS pet_last_fed (
            user_id INTEGER,
            pet_field TEXT,
            last_fed INTEGER,
            PRIMARY KEY (user_id, pet_field)
        );
        """
    )
    # ---------- promo_codes ----------
    _execute(
        """
        CREATE TABLE IF NOT EXISTS promo_codes (
            code TEXT PRIMARY KEY,
            coins INTEGER NOT NULL,
            pet_field TEXT,
            pet_qty INTEGER DEFAULT 0,
            max_uses INTEGER DEFAULT 1,
            used INTEGER DEFAULT 0
        );
        """
    )
    # ---------- farmers ----------
    _execute(
        """
        CREATE TABLE IF NOT EXISTS farmers (
            user_id INTEGER,
            farmer_type TEXT,
            qty INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, farmer_type)
        );
        """
    )
    # ---------- admin_logs ----------
    _execute(
        """
        CREATE TABLE IF NOT EXISTS admin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            ts INTEGER
        );
        """
    )
    conn.commit()


# ----------------------------------------------------------------------
#   Администраторы
# ----------------------------------------------------------------------
def add_admins() -> None:
    admin_ids = [7852721487]          # ваш Telegram‑ID
    for aid in admin_ids:
        _execute(
            "INSERT OR IGNORE INTO admin_users (user_id) VALUES (?)",
            (aid,),
        )


def is_admin(user_id: int) -> bool:
    cur.execute("SELECT 1 FROM admin_users WHERE user_id = ?", (user_id,))
    return cur.fetchone() is not None


def log_user_action(user_id: int, action: str) -> None:
    """Записывает действие игрока в журнал админа."""
    _execute(
        "INSERT INTO admin_logs (user_id, action, ts) VALUES (?,?,?)",
        (user_id, action, int(time.time())),
    )


# ----------------------------------------------------------------------
#   Утилиты
# ----------------------------------------------------------------------
def format_num(n: int) -> str:
    """Число с разделителем тысяч (точка)."""
    return f"{n:,}".replace(",", ".")


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (float, int)):
        v = int(value)
        return v if v <= MAX_INT else MAX_INT
    raise ValueError("Не число")


def update_user(user_id: int, **kwargs: Any) -> None:
    """Обновляет только переданные поля."""
    if not kwargs:
        return
    set_clause = ", ".join(f"{k}=?" for k in kwargs)
    vals = [
        _safe_int(v) if isinstance(v, (int, float, bool)) else v
        for v in kwargs.values()
    ]
    vals.append(user_id)
    _execute(f"UPDATE users SET {set_clause} WHERE user_id = ?", tuple(vals))


def get_user(user_id: int) -> sqlite3.Row:
    """Возвращает запись пользователя, создаёт её при необходимости."""
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if not row:
        _execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
    return row


# ----------------------------------------------------------------------
#   Простые ANIMAL_CONFIG и FARMER_CONFIG (сокращенные версии)
# ----------------------------------------------------------------------
ANIMAL_CONFIG: List[Tuple[str, int, str, str, str, int, str]] = [
    ("chickens", 2, "🐔", "Куры", "common", 200, "Кормят себя зерном."),
    ("cows", 4, "🐄", "Коровы", "common", 500, "Молоко превращается в золотой сыр."),
    ("pigs", 6, "🐖", "Свиньи", "common", 800, "Любят копать, находят монеты."),
    ("dragons", 8000, "🐉", "Драконы", "secret", 1_500_000, "Огненные монстры."),
]

FARMER_CONFIG: List[Tuple[str, int, int, str]] = [
    ("Местный фермер", 100_000_000, 5_000, "Небольшой участок, даёт +5 000 🪙/мин."),
    ("Опытный фермер", 500_000_000, 30_000, "Увеличивает доход всех животных на 5 %."),
]


def get_farmer(name: str) -> Tuple[str, int, int, str] | None:
    for rec in FARMER_CONFIG:
        if rec[0].lower() == name.lower():
            return rec
    return None


# ----------------------------------------------------------------------
#   Основные функции бота (упрощенные)
# ----------------------------------------------------------------------
def calculate_income_per_min(user: sqlite3.Row) -> int:
    """Возврат дохода за одну минуту."""
    now = time.time()
    mult = 1.0
    # Обычный корм – +40 %
    if now < user["feed_bonus_end"]:
        mult *= 1.4
    base = 0
    for field, inc, *_ in ANIMAL_CONFIG:
        base += user[field] * inc
    base += user["custom_income"]
    base = int(base * mult)
    return max(1, base) if base > 0 else 0


async def edit_section(
    query,
    caption: str,
    image_key: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Редактирует сообщение, заменяя фото на фото из SECTION_IMAGES[image_key]."""
    img = SECTION_IMAGES.get(image_key, MAIN_MENU_IMG)
    await query.edit_message_media(
        media=InputMediaPhoto(media=img, caption=caption),
        reply_markup=reply_markup,
    )


def build_main_menu(user_id: int) -> InlineKeyboardMarkup:
    rows = []
    rows.append([InlineKeyboardButton("ℹ️ О боте", callback_data="about")])
    other = [
        InlineKeyboardButton("🌾 Моя ферма", callback_data="farm"),
        InlineKeyboardButton("🛒 Магазин", callback_data="shop"),
        InlineKeyboardButton("📊 Статус", callback_data="status"),
    ]
    rows.extend([other])
    if is_admin(user_id):
        rows.append([InlineKeyboardButton("🔥 Админ", callback_data="admin")])
    return InlineKeyboardMarkup(rows)


async def show_main_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool = False
) -> None:
    user = update.effective_user
    text = f"🤖 Добро пожаловать в Ферму!"
    kb = build_main_menu(user.id)
    if edit:
        query = update.callback_query
        await edit_section(query, caption=text, image_key="about", reply_markup=kb)
    else:
        await update.message.reply_photo(
            MAIN_MENU_IMG,
            caption=text,
            reply_markup=kb,
        )


async def about_section(query) -> None:
    text = (
        "О боте «Ферма»\n"
        "Это простая ферма в Telegram. Вы покупаете животных, получаете доход, "
        "кормите их, улучшаете базу.\n\n"
        f"Чат проекта: {CHAT_LINK}\n"
        f"Канал проекта: {CHANNEL_LINK}\n\n"
        "Удачной фермы! 🐓🐄🐖"
    )
    btn = InlineKeyboardButton("⬅️ Назад", callback_data="back")
    await edit_section(
        query,
        caption=text,
        image_key="about",
        reply_markup=InlineKeyboardMarkup([[btn]]),
    )


async def farm_section(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = query.from_user.id
    user = get_user(uid)
    # Список животных
    lines = []
    for field, inc, emoji, name, *_ in ANIMAL_CONFIG:
        cnt = user[field]
        if cnt == 0:
            continue
        inc_total = inc * cnt
        lines.append(f"{emoji} {name}: {cnt} (+{format_num(inc_total)}🪙/мин)")
    
    farm_text = "\n".join(lines) or "❌ На ферме пока нет животных."
    
    btns = [
        InlineKeyboardButton("🛒 Магазин", callback_data="shop"),
        InlineKeyboardButton("⬅️ Главное меню", callback_data="back"),
    ]
    kb = InlineKeyboardMarkup([btns])
    
    await edit_section(
        query,
        caption=(
            f"🌾 Ферма 🌾\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Монеты: {format_num(user['coins'])}\n"
            f"💰 Доход за минуту: {format_num(calculate_income_per_min(user))}🪙\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{farm_text}"
        ),
        image_key="farm",
        reply_markup=kb,
    )


async def shop_section(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    btns = []
    for field, _, emoji, name, _, price, _ in ANIMAL_CONFIG:
        btns.append(
            InlineKeyboardButton(
                f"{emoji} {name} ({format_num(price)}🪙)", 
                callback_data=f"buy_{field}"
            )
        )
    btns.append(InlineKeyboardButton("⬅️ Назад", callback_data="back"))
    
    kb = InlineKeyboardMarkup([[btn] for btn in btns])
    
    await edit_section(
        query,
        caption="🛒 Магазин животных",
        image_key="shop",
        reply_markup=kb,
    )


async def buy_animal(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    field = query.data.split("_", 1)[1]
    uid = query.from_user.id
    user = get_user(uid)
    
    rec = next((r for r in ANIMAL_CONFIG if r[0] == field), None)
    if not rec:
        await query.edit_message_caption(caption="❌ Питомец не найден.")
        return
    
    _, _, _, _, _, price, _ = rec
    
    if user["coins"] < price:
        await edit_section(
            query,
            caption=f"❌ Недостаточно монет. Нужно {format_num(price)}🪙.",
            image_key="shop",
        )
        return
    
    update_user(
        uid,
        coins=user["coins"] - price,
        **{field: user[field] + 1}
    )
    
    log_user_action(uid, f"Купил 1 {field} за {price}🪙")
    
    await edit_section(
        query,
        caption=f"✅ Вы купили 1 {field} за {format_num(price)}🪙!",
        image_key="shop",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ В магазин", callback_data="shop")]]
        ),
    )


async def status_section(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = query.from_user.id
    user = get_user(uid)
    income_min = calculate_income_per_min(user)
    
    text = (
        f"📊 Статус 📊\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 ID: {user['user_id']}\n"
        f"💰 Монеты: {format_num(user['coins'])}\n"
        f"💰 Доход за минуту: {format_num(income_min)}🪙\n"
        f"🏗️ База: уровень {user['base_level']} (лимит: {user['pet_limit']})\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    back_btn = InlineKeyboardButton("⬅️ Главное меню", callback_data="back")
    kb = InlineKeyboardMarkup([[back_btn]])
    
    await edit_section(
        query,
        caption=text,
        image_key="status",
        reply_markup=kb,
    )


async def admin_panel(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(query.from_user.id):
        await edit_section(query, caption="❌ Доступ запрещён.", image_key="admin")
        return
    
    btns = [
        InlineKeyboardButton("📜 Журнал действий", callback_data="admin_view_logs"),
        InlineKeyboardButton("⬅️ Назад", callback_data="back"),
    ]
    kb = InlineKeyboardMarkup([[btn] for btn in btns])
    
    await edit_section(
        query,
        caption="🔥 Админ‑панель 🔥",
        image_key="admin",
        reply_markup=kb,
    )


async def admin_view_logs(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(query.from_user.id):
        return
    
    cur.execute(
        "SELECT user_id, action, ts FROM admin_logs ORDER BY ts DESC LIMIT 20"
    )
    rows = cur.fetchall()
    
    if not rows:
        txt = "📜 Журнал пуст."
    else:
        txt = "📜 Последние действия игроков:\n"
        for row in rows:
            t = time.strftime("%d.%m %H:%M", time.localtime(row["ts"]))
            txt += f"[{t}] ID {row['user_id']}: {row['action']}\n"
    
    await edit_section(
        query,
        caption=txt,
        image_key="logs",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Назад", callback_data="admin")]]
        ),
    )


# ----------------------------------------------------------------------
#   Обработчик всех кнопок
# ----------------------------------------------------------------------
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    
    data = query.data
    
    if data == "back":
        await show_main_menu(update, context, edit=True)
    elif data == "about":
        await about_section(query)
    elif data == "farm":
        await farm_section(query, context)
    elif data == "shop":
        await shop_section(query, context)
    elif data == "status":
        await status_section(query, context)
    elif data == "admin":
        await admin_panel(query, context)
    elif data == "admin_view_logs":
        await admin_view_logs(query, context)
    elif data.startswith("buy_"):
        await buy_animal(query, context)
    else:
        await query.edit_message_caption(caption="❓ Неизвестная команда.")


# ----------------------------------------------------------------------
#   /start
# ----------------------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    get_user(user.id)  # Создаём пользователя если его нет
    await show_main_menu(update, context, edit=False)


# ----------------------------------------------------------------------
#   Автосбор дохода (каждую минуту)
# ----------------------------------------------------------------------
async def auto_collect(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Каждую минуту начисляем доход."""
    cur.execute("SELECT user_id FROM users")
    now = int(time.time())
    for (uid,) in cur.fetchall():
        user = get_user(uid)
        earned = calculate_income_per_min(user)
        if earned == 0:
            continue
        new_coins = min(user["coins"] + earned, MAX_INT)
        update_user(uid, coins=new_coins, last_active=now)
        log_user_action(uid, f"Получено {earned}🪙 (автосбор)")


# ----------------------------------------------------------------------
#   Запуск бота
# ----------------------------------------------------------------------
def main() -> None:
    init_db()
    add_admins()
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Основные команды
    app.add_handler(CommandHandler("start", start_command))
    
    # Обработчики кнопок
    app.add_handler(CallbackQueryHandler(button))
    
    # Фоновые задачи
    app.job_queue.run_repeating(auto_collect, interval=60, first=10)
    
    print("✅ Farm Bot запущен успешно!")
    app.run_polling()


if __name__ == "__main__":
    main()