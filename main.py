import sqlite3
import requests
import os
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
import matplotlib.pyplot as plt  # Для создания графиков
from io import BytesIO  # Для отправки изображений

# Загрузка переменных окружения
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID"))  # Ваш уникальный user_id

# Подключение к базе данных
conn = sqlite3.connect("btc_portfolio.db", check_same_thread=False)
cursor = conn.cursor()

# Создание таблицы для хранения данных
cursor.execute("""
CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount REAL,
    price REAL,
    total REAL,
    date TEXT
)
""")
conn.commit()

# Состояния для диалога добавления покупки
AMOUNT, PRICE, MOONSHOT_PRICE = range(3)

# Функция для получения текущего курса BTC
def get_btc_price():
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": "bitcoin", "vs_currencies": "usd"}
    response = requests.get(url, params=params).json()
    return response["bitcoin"]["usd"]

# Проверка доступа
def is_user_allowed(user_id):
    return user_id == ALLOWED_USER_ID

# Главное меню
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_user_allowed(user_id):
        await update.message.reply_text("❌ Извините, этот бот доступен только для владельца.")
        return

    keyboard = [
        [KeyboardButton("➕ Добавить покупку"), KeyboardButton("📊 Прогресс")],
        [KeyboardButton("📅 История"), KeyboardButton("🚀 Moonshot")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("🏠 Главное меню:", reply_markup=reply_markup)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_user_allowed(user_id):
        await update.message.reply_text("❌ Извините, этот бот доступен только для владельца.")
        return

    await update.message.reply_text(
        "🚀 Привет! Я — ваш персональный BTC Moonshot Bot.\n"
        "Моя цель — помочь вам достичь $100,000, регулярно покупая BTC."
    )
    await main_menu(update, context)

# Добавление покупки (начало диалога)
async def add_purchase_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_user_allowed(user_id):
        await update.message.reply_text("❌ Извините, этот бот доступен только для владельца.")
        return

    await update.message.reply_text("Сколько BTC вы купили? 🪙")
    return AMOUNT

# Добавление покупки (ввод количества)
async def add_purchase_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_user_allowed(user_id):
        await update.message.reply_text("❌ Извините, этот бот доступен только для владельца.")
        return

    try:
        amount = float(update.message.text)
        context.user_data["amount"] = amount
        await update.message.reply_text("По какой цене вы купили? 💵")
        return PRICE
    except ValueError:
        await update.message.reply_text("⚠️ Введите корректное число.")
        return AMOUNT

# Добавление покупки (ввод цены)
async def add_purchase_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_user_allowed(user_id):
        await update.message.reply_text("❌ Извините, этот бот доступен только для владельца.")
        return

    try:
        price = float(update.message.text)
        amount = context.user_data["amount"]
        total = amount * price

        # Сохраняем данные в базу
        cursor.execute("""
        INSERT INTO purchases (amount, price, total, date)
        VALUES (?, ?, ?, datetime('now'))
        """, (amount, price, total))
        conn.commit()

        await update.message.reply_text(
            f"💰 Покупка добавлена!\n"
            f"Количество: {amount:.8f} BTC\n"
            f"Цена покупки: ${price:,.0f}\n"
            f"Сумма: ${total:,.0f}"
        )
        await main_menu(update, context)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("⚠️ Введите корректное число.")
        return PRICE

# Проверка прогресса
async def progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_user_allowed(user_id):
        await update.message.reply_text("❌ Извините, этот бот доступен только для владельца.")
        return

    cursor.execute("SELECT SUM(amount), SUM(total) FROM purchases")
    result = cursor.fetchone()
    total_btc = result[0] or 0
    total_invested = result[1] or 0

    current_price = get_btc_price()
    current_value = total_btc * current_price
    profit = current_value - total_invested
    profit_percent = (profit / total_invested * 100) if total_invested > 0 else 0

    goal = 100000  # Цель: $100,000
    progress_percent = (current_value / goal) * 100 if goal > 0 else 0

    # Текстовое сообщение
    text_message = (
        f"📊 Ваш портфель:\n"
        f"- Общая сумма инвестиций: ${total_invested:,.0f}\n"
        f"- Текущая стоимость портфеля: ${current_value:,.0f} ({profit:+,.0f}, {profit_percent:+.1f}%)\n"
        f"- BTC в портфеле: {total_btc:.8f}\n"
        f"- До цели ($100,000): ${goal - current_value:,.0f}\n\n"
        f"🎯 Прогресс: {progress_percent:.1f}%"
    )

    await update.message.reply_text(text_message)

    # Круговая диаграмма прогресса
    labels = ["Текущая стоимость", "Осталось до цели"]
    values = [current_value, max(goal - current_value, 0)]  # Остаток не может быть отрицательным
    colors = ["#4CAF50", "#FFC107"]  # Зеленый и желтый цвета
    explode = (0.1, 0)  # Выделение первого сегмента

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(
        values,
        explode=explode,
        labels=labels,
        autopct="%1.1f%%",
        startangle=90,
        colors=colors,
        textprops={"fontsize": 12}
    )
    ax.set_title("Прогресс к цели ($100,000)", fontsize=14)

    # Сохраняем график в буфер
    buffer = BytesIO()
    plt.savefig(buffer, format="png")
    buffer.seek(0)
    plt.close()

    # Отправляем график
    await update.message.reply_photo(photo=buffer)

# Обработчик кнопки "📅 История"
async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_user_allowed(user_id):
        await update.message.reply_text("❌ Извините, этот бот доступен только для владельца.")
        return

    # Получаем все покупки из базы данных
    cursor.execute("SELECT amount, price, total, date FROM purchases ORDER BY date DESC")
    purchases = cursor.fetchall()

    if not purchases:
        await update.message.reply_text("⚠️ У вас пока нет записей о покупках.")
        return

    # Формируем текст для отправки
    history_text = "📅 История покупок:\n\n"
    for purchase in purchases:
        amount, price, total, date = purchase
        history_text += (
            f"Дата: {date}\n"
            f"Количество: {amount:.8f} BTC\n"
            f"Цена покупки: ${price:,.0f}\n"
            f"Сумма: ${total:,.0f}\n"
            "—\n"
        )

    await update.message.reply_text(history_text)

# Moonshot Meter
async def moonshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_user_allowed(user_id):
        await update.message.reply_text("❌ Извините, этот бот доступен только для владельца.")
        return

    await update.message.reply_text("🚀 До какой цены может вырасти BTC?")
    return MOONSHOT_PRICE

async def moonshot_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_user_allowed(user_id):
        await update.message.reply_text("❌ Извините, этот бот доступен только для владельца.")
        return

    try:
        target_price = float(update.message.text)
        cursor.execute("SELECT SUM(amount) FROM purchases")
        total_btc = cursor.fetchone()[0] or 0

        current_value = total_btc * target_price
        profit = current_value - (get_btc_price() * total_btc)

        await update.message.reply_text(
            f"🚀 Если цена BTC достигнет ${target_price:,.0f}:\n"
            f"- Ваш портфель будет стоить: ${current_value:,.0f}\n"
            f"- Прибыль: +${profit:,.0f}"
        )
        await main_menu(update, context)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("⚠️ Введите корректное число.")
        return MOONSHOT_PRICE

# Настройка бота
def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Диалог добавления покупки
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Добавить покупку$"), add_purchase_start)],
        states={
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_purchase_amount)],
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_purchase_price)]
        },
        fallbacks=[]
    )

    # Диалог Moonshot Meter
    moonshot_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🚀 Moonshot$"), moonshot)],
        states={
            MOONSHOT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, moonshot_price)]
        },
        fallbacks=[]
    )

    application.add_handler(conv_handler)
    application.add_handler(moonshot_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex("^📊 Прогресс$"), progress))
    application.add_handler(MessageHandler(filters.Regex("^📅 История$"), history))  # Добавляем обработчик истории

    application.run_polling()

if __name__ == "__main__":
    main()