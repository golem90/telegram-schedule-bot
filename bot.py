import asyncio
import json
import os
from datetime import datetime, timedelta
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import schedule
import threading
import time

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(os.getenv("ADMIN_ID"))]

SETTINGS_FILE = "settings.json"

SCHEDULE = [
    ("06:30", "🌅 ПОДЪЁМ: вставайте, гигиена, стакан воды, зарядка"),
    ("06:35", "📓 УТРЕННИЙ ДНЕВНИК: планы, благодарности, цели"),
    ("07:00", "🍳 ЗАВТРАК: белки + углеводы + овощи"),
    ("07:30", "🚗 ОТВЕЗТИ ДОЧКУ В ШКОЛУ"),
    ("08:00", "🏊 БАССЕЙН: разминка → 30-40 мин плавание"),
    ("09:00", "🥤 ПЕРЕКУС: протеин/йогурт + медитация"),
    ("09:30", "📈 ТОРГОВЛЯ сессия 1: 60 минут"),
    ("11:00", "☕ ПЕРЕРЫВ: 15 мин прогулка"),
    ("11:15", "📉 ТОРГОВЛЯ сессия 2: 90 минут"),
    ("13:00", "🍽️ ОБЕД: рыба/курица + салат"),
    ("14:00", "🧹 УБОРКА: 1-2 зоны"),
    ("15:00", "📖 ЧТЕНИЕ: лучшее время для усвоения"),
    ("16:00", "🏫 ЗАБРАТЬ ДОЧКУ ИЗ ШКОЛЫ"),
    ("16:30", "🥋 КРУЖОК КУДО"),
    ("18:00", "🍲 УЖИН: лёгкий, семья за столом"),
    ("19:00", "🎮 ОТДЫХ: игры/аудиокнига"),
    ("20:00", "📘 ВЕЧЕРНИЙ ДНЕВНИК: итоги дня"),
    ("20:30", "🕯️ СЕМЕЙНОЕ ВРЕМЯ"),
    ("22:00", "💤 ОТБОЙ: гаджеты выключены")
]

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r') as f:
            return json.load(f)
    return {"enabled": True, "delay_minutes": 5, "users": []}

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f)

settings = load_settings()
bot = None
scheduled_jobs = []

def clear_schedule():
    for job in scheduled_jobs:
        schedule.cancel_job(job)
    scheduled_jobs.clear()

def setup_schedule():
    clear_schedule()
    if not settings.get("enabled", True):
        return
    delay = settings.get("delay_minutes", 5)
    for time_str, message in SCHEDULE:
        hour, minute = map(int, time_str.split(':'))
        new_minute = minute + delay
        new_hour = hour + new_minute // 60
        new_minute %= 60
        send_time = f"{new_hour:02d}:{new_minute:02d}"
        job = schedule.every().day.at(send_time).do(
            lambda t=time_str, m=message, d=delay: send_notification(t, m, d)
        )
        scheduled_jobs.append(job)

async def send_notification(original_time, message, delay):
    for user_id in settings.get("users", []):
        try:
            text = f"⏰ [ЗАДЕРЖКА {delay} МИН]\nОригинальное время: {original_time}\nСейчас: {datetime.now().strftime('%H:%M')}\n\n{message}"
            await bot.send_message(chat_id=user_id, text=text)
        except Exception as e:
            print(f"Ошибка: {e}")

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in ADMIN_IDS:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton("📊 Статус", callback_data="status")]
        ])
        await update.message.reply_text("🤖 Бот-админ запущен!", reply_markup=kb)
    else:
        if user_id not in settings["users"]:
            settings["users"].append(user_id)
            save_settings(settings)
            await update.message.reply_text("✅ Вы добавлены в список уведомлений!")

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    status = "🟢 ВКЛЮЧЕНЫ" if settings["enabled"] else "🔴 ВЫКЛЮЧЕНЫ"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{'🔴' if settings['enabled'] else '🟢'} {'ВЫКЛЮЧИТЬ' if settings['enabled'] else 'ВКЛЮЧИТЬ'}", callback_data="toggle")],
        [InlineKeyboardButton(f"⏰ Задержка: {settings['delay_minutes']} мин", callback_data="set_delay")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="users_list")],
        [InlineKeyboardButton("◀️ Назад", callback_data="main_menu")]
    ])
    await query.edit_message_text(f"⚙️ *Настройки*\nУведомления: {status}\nЗадержка: {settings['delay_minutes']} мин\nПользователей: {len(settings['users'])}", reply_markup=kb, parse_mode="Markdown")

async def toggle_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    settings["enabled"] = not settings["enabled"]
    save_settings(settings)
    if settings["enabled"]:
        setup_schedule()
        await query.edit_message_text("✅ Уведомления ВКЛЮЧЕНЫ")
    else:
        clear_schedule()
        await query.edit_message_text("❌ Уведомления ВЫКЛЮЧЕНЫ")
    await asyncio.sleep(2)
    await settings_menu(update, context)

async def set_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("5 минут", callback_data="delay_5")],
        [InlineKeyboardButton("10 минут", callback_data="delay_10")],
        [InlineKeyboardButton("15 минут", callback_data="delay_15")],
        [InlineKeyboardButton("0 минут (точно)", callback_data="delay_0")],
        [InlineKeyboardButton("◀️ Назад", callback_data="settings")]
    ])
    await query.edit_message_text("⏰ *Выберите задержку*", reply_markup=kb, parse_mode="Markdown")

async def set_delay_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    delay = int(query.data.split("_")[1])
    settings["delay_minutes"] = delay
    save_settings(settings)
    if settings["enabled"]:
        setup_schedule()
    await query.edit_message_text(f"✅ Задержка: {delay} минут")
    await asyncio.sleep(1.5)
    await settings_menu(update, context)

async def users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "👥 *Пользователи:*\n\n" + "\n".join([f"{i+1}. ID: `{uid}`" for i, uid in enumerate(settings["users"])]) if settings["users"] else "📭 Нет пользователей"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="settings")]])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    status_text = "🟢 ВКЛЮЧЕНЫ" if settings["enabled"] else "🔴 ВЫКЛЮЧЕНЫ"
    text = f"📊 *Статус*\nУведомления: {status_text}\nЗадержка: {settings['delay_minutes']} мин\nПользователей: {len(settings['users'])}\nСобытий: {len(SCHEDULE)}"
    await query.edit_message_text(text, parse_mode="Markdown")

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton("📊 Статус", callback_data="status")]
    ])
    await query.edit_message_text("🤖 Главное меню", reply_markup=kb)

def main():
    global bot
    app = Application.builder().token(TOKEN).build()
    bot = app.bot
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(settings_menu, pattern="^settings$"))
    app.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(toggle_notifications, pattern="^toggle$"))
    app.add_handler(CallbackQueryHandler(set_delay, pattern="^set_delay$"))
    app.add_handler(CallbackQueryHandler(set_delay_value, pattern="^delay_"))
    app.add_handler(CallbackQueryHandler(users_list, pattern="^users_list$"))
    app.add_handler(CallbackQueryHandler(status, pattern="^status$"))
    setup_schedule()
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    app.run_polling()

if __name__ == "__main__":
    main()
