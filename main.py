# File: main.py — Telegram-бот музея с операторским режимом (активный диалог)

import os
import csv
from datetime import datetime

from dotenv import load_dotenv
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    filters,
)

# ======================
# ENV
# ======================

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

if not TELEGRAM_TOKEN or not ADMIN_CHAT_ID:
    print("❌ Добавьте TELEGRAM_TOKEN и ADMIN_CHAT_ID в .env")
    raise SystemExit(1)

ADMIN_CHAT_ID = int(ADMIN_CHAT_ID)

# ======================
# STATES
# ======================

FAQ_MODE = 1
LEAD_NAME = 2

LEADS_FILE = "leads.csv"

# ======================
# STORAGE
# ======================

ACTIVE_USERS = {}              # user_id -> {name, username}
ACTIVE_DIALOG_USER_ID = None   # текущий пользователь для ответа

# ======================
# FAQ
# ======================

FAQ_ANSWERS = {
    "время": "Музей открыт со вторника по воскресенье с 10:00 до 18:00.",
    "адрес": "Мы находимся в центре города. Адрес подскажет сотрудник музея.",
    "билет": "Информацию о билетах можно уточнить у сотрудника музея.",
}

# ======================
# KEYBOARDS
# ======================

def main_menu():
    return ReplyKeyboardMarkup(
        [["Задать вопрос"], ["Позвать сотрудника музея"]],
        resize_keyboard=True,
    )


def back_menu():
    return ReplyKeyboardMarkup([["В меню"]], resize_keyboard=True)


def admin_users_keyboard():
    buttons = []
    for uid, data in ACTIVE_USERS.items():
        label = f"👤 {data.get('name')} (@{data.get('username')})"
        buttons.append(
            [InlineKeyboardButton(label, callback_data=f"select_user:{uid}")]
        )
    return InlineKeyboardMarkup(buttons)

# ======================
# CSV
# ======================

def ensure_csv():
    if not os.path.exists(LEADS_FILE):
        with open(LEADS_FILE, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(
                ["created_at", "name", "tg_user_id", "tg_username"]
            )

# ======================
# HANDLERS
# ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Добро пожаловать! Я помогу задать вопрос или связаться с сотрудником музея.",
        reply_markup=main_menu(),
    )
    return ConversationHandler.END


# ===== ЗАДАТЬ ВОПРОС =====

async def faq_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Пожалуйста, напишите ваш вопрос.",
        reply_markup=back_menu(),
    )
    return FAQ_MODE


async def faq_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    if text == "в меню":
        await update.message.reply_text(
            "Вы вернулись в меню.",
            reply_markup=main_menu(),
        )
        return ConversationHandler.END

    for key, answer in FAQ_ANSWERS.items():
        if key in text:
            await update.message.reply_text(answer)
            return FAQ_MODE

    await update.message.reply_text(
        "Я передам ваш вопрос сотруднику музея.",
        reply_markup=main_menu(),
    )
    return ConversationHandler.END


# ===== ПОЗВАТЬ СОТРУДНИКА =====

async def lead_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Пожалуйста, напишите, как Вас зовут.",
        reply_markup=back_menu(),
    )
    return LEAD_NAME


async def lead_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "В меню":
        await update.message.reply_text(
            "Вы вернулись в меню.",
            reply_markup=main_menu(),
        )
        return ConversationHandler.END

    user = update.message.from_user
    name = update.message.text.strip()

    ensure_csv()
    with open(LEADS_FILE, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(
            [datetime.now().isoformat(), name, user.id, user.username]
        )

    ACTIVE_USERS[user.id] = {
        "name": name,
        "username": user.username,
    }

    await context.bot.send_message(
        ADMIN_CHAT_ID,
        (
            "🙋 Посетитель хочет связаться с сотрудником музея\n\n"
            f"Имя: {name}\n"
            f"Username: @{user.username}\n\n"
            "Выберите посетителя для начала диалога:"
        ),
        reply_markup=admin_users_keyboard(),
    )

    await update.message.reply_text(
        "✅ Заявка принята, мы скоро с Вами свяжемся.",
        reply_markup=main_menu(),
    )

    return ConversationHandler.END


# ===== ПОЛЬЗОВАТЕЛЬ → АДМИН =====

async def user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user

    ACTIVE_USERS.setdefault(
        user.id,
        {"name": user.first_name, "username": user.username},
    )

    await context.bot.send_message(
        ADMIN_CHAT_ID,
        (
            "💬 Сообщение от посетителя\n\n"
            f"Имя: {ACTIVE_USERS[user.id].get('name')}\n"
            f"Username: @{ACTIVE_USERS[user.id].get('username')}\n\n"
            f"Текст:\n{update.message.text}"
        ),
        reply_markup=admin_users_keyboard(),
    )


# ===== АДМИН → ПОЛЬЗОВАТЕЛЮ =====

async def select_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ACTIVE_DIALOG_USER_ID

    query = update.callback_query
    await query.answer()

    ACTIVE_DIALOG_USER_ID = int(query.data.split(":")[1])
    data = ACTIVE_USERS.get(ACTIVE_DIALOG_USER_ID)

    await context.bot.send_message(
        ACTIVE_DIALOG_USER_ID,
        "👋 К вам подключился сотрудник музея. Вы можете задать свой вопрос."
    )

    await query.message.reply_text(
        f"✅ Активный диалог:\n"
        f"{data.get('name')} (@{data.get('username')})\n\n"
        "Теперь вы можете писать обычным текстом."
    )


async def admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ACTIVE_DIALOG_USER_ID:
        await update.message.reply_text(
            "❗ Сначала выберите посетителя, чтобы начать диалог."
        )
        return

    await context.bot.send_message(
        ACTIVE_DIALOG_USER_ID,
        update.message.text,
    )

# ======================
# MAIN
# ======================

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(select_user, pattern="^select_user:"))

    app.add_handler(
        ConversationHandler(
            entry_points=[MessageHandler(filters.Regex("^Задать вопрос$"), faq_start)],
            states={FAQ_MODE: [MessageHandler(filters.TEXT, faq_answer)]},
            fallbacks=[],
        )
    )

    app.add_handler(
        ConversationHandler(
            entry_points=[
                MessageHandler(filters.Regex("^Позвать сотрудника музея$"), lead_start)
            ],
            states={LEAD_NAME: [MessageHandler(filters.TEXT, lead_name)]},
            fallbacks=[],
        )
    )

    # 🔒 ЖЁСТКОЕ РАЗДЕЛЕНИЕ
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.Chat(ADMIN_CHAT_ID), user_message)
    )
    app.add_handler(
        MessageHandler(filters.TEXT & filters.Chat(ADMIN_CHAT_ID), admin_message)
    )

    print("✅ Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
