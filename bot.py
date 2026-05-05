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

DATA_FILE = "schedule.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {
        "enabled": True,
        "events": [
            {"id": 1, "time_start": "06:30", "time_end": "06:35", "title": "🌅 Подъём", "notification_enabled": True, "notification_minutes_before": 0},
            {"id": 2, "time_start": "06:35", "time_end": "06:40", "title": "📓 Утренний дневник", "notification_enabled": True, "notification_minutes_before": 0},
            {"id": 3, "time_start": "07:00", "time_end": "07:15", "title": "🍳 Завтрак", "notification_enabled": True, "notification_minutes_before": 0},
            {"id": 4, "time_start": "07:30", "time_end": "07:45", "title": "🚗 Отвезти дочку в школу", "notification_enabled": True, "notification_minutes_before": 5},
            {"id": 5, "time_start": "08:00", "time_end": "08:45", "title": "🏊 Бассейн", "notification_enabled": True, "notification_minutes_before": 10},
            {"id": 6, "time_start": "09:30", "time_end": "11:00", "title": "📈 Торговля сессия 1", "notification_enabled": True, "notification_minutes_before": 5},
            {"id": 7, "time_start": "11:15", "time_end": "12:45", "title": "📉 Торговля сессия 2", "notification_enabled": True, "notification_minutes_before": 5},
            {"id": 8, "time_start": "13:00", "time_end": "13:30", "title": "🍽️ Обед", "notification_enabled": True, "notification_minutes_before": 0},
            {"id": 9, "time_start": "14:00", "time_end": "15:00", "title": "🧹 Уборка", "notification_enabled": True, "notification_minutes_before": 5},
            {"id": 10, "time_start": "15:00", "time_end": "16:00", "title": "📖 Чтение", "notification_enabled": True, "notification_minutes_before": 5},
            {"id": 11, "time_start": "16:30", "time_end": "17:30", "title": "🥋 Кружок кудо", "notification_enabled": True, "notification_minutes_before": 10},
            {"id": 12, "time_start": "18:00", "time_end": "18:30", "title": "🍲 Ужин", "notification_enabled": True, "notification_minutes_before": 5},
            {"id": 13, "time_start": "19:00", "time_end": "20:00", "title": "🎮 Отдых", "notification_enabled": True, "notification_minutes_before": 5},
            {"id": 14, "time_start": "20:00", "time_end": "20:30", "title": "📘 Вечерний дневник", "notification_enabled": True, "notification_minutes_before": 5},
            {"id": 15, "time_start": "22:00", "time_end": "22:00", "title": "💤 Отбой", "notification_enabled": True, "notification_minutes_before": 15}
        ],
        "users": [],
        "next_id": 16
    }

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

data = load_data()
bot = None
scheduled_jobs = {}

def clear_schedule():
    for job_id, job in scheduled_jobs.items():
        schedule.cancel_job(job)
    scheduled_jobs.clear()

def setup_schedule():
    clear_schedule()
    if not data.get("enabled", True):
        return
    
    for event in data["events"]:
        if not event.get("notification_enabled", True):
            continue
        
        time_str = event["time_start"]
        hour, minute = map(int, time_str.split(':'))
        minutes_before = event.get("notification_minutes_before", 0)
        
        # Вычисляем время отправки уведомления
        send_minute = minute - minutes_before
        send_hour = hour
        if send_minute < 0:
            send_hour -= 1
            send_minute += 60
            if send_hour < 0:
                send_hour = 23
        
        send_time = f"{send_hour:02d}:{send_minute:02d}"
        
        job = schedule.every().day.at(send_time).do(
            lambda e=event: send_event_notification(e)
        )
        scheduled_jobs[event["id"]] = job

async def send_event_notification(event):
    for user_id in data.get("users", []):
        try:
            before_text = ""
            minutes = event.get("notification_minutes_before", 0)
            if minutes > 0:
                before_text = f" (за {minutes} мин)"
            
            text = f"🔔 {event['title']} {before_text}\n"
            text += f"⏰ Время: {event['time_start']} - {event.get('time_end', event['time_start'])}\n"
            text += f"📝 Не забудьте!"
            
            await bot.send_message(chat_id=user_id, text=text)
        except Exception as e:
            print(f"Ошибка: {e}")

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

# Команды бота
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in ADMIN_IDS:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📅 Распорядок", callback_data="show_schedule")],
            [InlineKeyboardButton("✏️ Редактировать", callback_data="edit_menu")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton("📊 Статус", callback_data="status")]
        ])
        await update.message.reply_text("🤖 *Бот распорядка дня*\n\nВыберите действие:", reply_markup=kb, parse_mode="Markdown")
    else:
        if user_id not in data["users"]:
            data["users"].append(user_id)
            save_data(data)
            await update.message.reply_text("✅ Вы добавлены в список уведомлений!")

async def show_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = "*📅 Распорядок дня*\n\n"
    for i, event in enumerate(data["events"], 1):
        icon = "🔔" if event.get("notification_enabled", True) else "🔕"
        before = event.get("notification_minutes_before", 0)
        before_text = f" (за {before} мин)" if before > 0 else ""
        text += f"{i}. {icon} {event['title']}\n   ⏰ {event['time_start']} - {event.get('time_end', event['time_start'])}{before_text}\n\n"
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="main_menu")]])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

async def edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить событие", callback_data="add_event")],
        [InlineKeyboardButton("✏️ Редактировать событие", callback_data="edit_event")],
        [InlineKeyboardButton("🗑️ Удалить событие", callback_data="delete_event")],
        [InlineKeyboardButton("◀️ Назад", callback_data="main_menu")]
    ])
    await query.edit_message_text("*✏️ Редактирование расписания*\n\nВыберите действие:", reply_markup=kb, parse_mode="Markdown")

async def list_events_for_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action = query.data.split("_")[1]  # edit или delete
    
    buttons = []
    for event in data["events"]:
        buttons.append([InlineKeyboardButton(f"{event['time_start']} - {event['title']}", callback_data=f"{action}_event_{event['id']}")])
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="edit_menu")])
    
    kb = InlineKeyboardMarkup(buttons)
    text = "Выберите событие для редактирования:" if action == "edit" else "Выберите событие для удаления:"
    await query.edit_message_text(text, reply_markup=kb)

async def edit_event_form(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    event_id = int(query.data.split("_")[2])
    event = next((e for e in data["events"] if e["id"] == event_id), None)
    if not event:
        await query.edit_message_text("Ошибка: событие не найдено")
        return
    
    context.user_data["editing_event_id"] = event_id
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Изменить название", callback_data=f"edit_title_{event_id}")],
        [InlineKeyboardButton("⏰ Изменить время начала", callback_data=f"edit_start_{event_id}")],
        [InlineKeyboardButton("⏰ Изменить время окончания", callback_data=f"edit_end_{event_id}")],
        [InlineKeyboardButton("🔔 Уведомление за (мин)", callback_data=f"edit_before_{event_id}")],
        [InlineKeyboardButton(f"{'🔔 Вкл' if event['notification_enabled'] else '🔕 Выкл'} уведомления", callback_data=f"toggle_notif_{event_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="edit_menu")]
    ])
    
    text = f"*Редактирование:*\n\n"
    text += f"📝 {event['title']}\n"
    text += f"⏰ {event['time_start']} - {event.get('time_end', event['time_start'])}\n"
    text += f"🔔 Уведомление: {'за ' + str(event.get('notification_minutes_before', 0)) + ' мин' if event.get('notification_minutes_before', 0) > 0 else 'точно в время'}\n"
    text += f"📢 Уведомления: {'Включены' if event.get('notification_enabled', True) else 'Выключены'}"
    
    await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

async def add_event_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["adding_event"] = True
    await query.edit_message_text(
        "📝 *Добавление события*\n\n"
        "Отправьте сообщение в формате:\n"
        "`Название | Время начала | Время окончания | Уведомление за (мин)`\n\n"
        "Пример:\n"
        "`Прогулка | 17:00 | 18:00 | 10`\n\n"
        "Уведомление за 0 мин = точно в время\n"
        "Для отмены отправьте /cancel",
        parse_mode="Markdown"
    )

async def handle_add_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("adding_event"):
        return
    
    text = update.message.text.strip()
    if text == "/cancel":
        context.user_data["adding_event"] = False
        await update.message.reply_text("❌ Добавление отменено")
        return
    
    try:
        parts = text.split("|")
        if len(parts) < 4:
            await update.message.reply_text("❌ Неверный формат. Используйте: `Название | 08:00 | 09:00 | 5`")
            return
        
        title = parts[0].strip()
        start_time = parts[1].strip()
        end_time = parts[2].strip()
        minutes_before = int(parts[3].strip())
        
        # Валидация времени
        datetime.strptime(start_time, "%H:%M")
        datetime.strptime(end_time, "%H:%M")
        
        new_id = data["next_id"]
        data["next_id"] += 1
        
        data["events"].append({
            "id": new_id,
            "title": title,
            "time_start": start_time,
            "time_end": end_time,
            "notification_enabled": True,
            "notification_minutes_before": minutes_before
        })
        save_data(data)
        setup_schedule()
        
        await update.message.reply_text(f"✅ Событие \"{title}\" добавлено!")
    except ValueError:
        await update.message.reply_text("❌ Ошибка: неверный формат времени (используйте ЧЧ:ММ) или числа")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
    
    context.user_data["adding_event"] = False

async def delete_event_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    event_id = int(query.data.split("_")[2])
    event = next((e for e in data["events"] if e["id"] == event_id), None)
    
    if not event:
        await query.edit_message_text("Ошибка: событие не найдено")
        return
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_del_{event_id}")],
        [InlineKeyboardButton("❌ Нет", callback_data="edit_menu")]
    ])
    
    await query.edit_message_text(f"Удалить событие \"{event['title']}\"?", reply_markup=kb)

async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    event_id = int(query.data.split("_")[2])
    event = next((e for e in data["events"] if e["id"] == event_id), None)
    
    if event:
        data["events"] = [e for e in data["events"] if e["id"] != event_id]
        save_data(data)
        setup_schedule()
        await query.edit_message_text(f"✅ Событие \"{event['title']}\" удалено")
    else:
        await query.edit_message_text("Ошибка: событие не найдено")

async def toggle_event_notification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    event_id = int(query.data.split("_")[2])
    event = next((e for e in data["events"] if e["id"] == event_id), None)
    
    if event:
        event["notification_enabled"] = not event.get("notification_enabled", True)
        save_data(data)
        setup_schedule()
        await query.edit_message_text(f"✅ Уведомления для \"{event['title']}\" {'включены' if event['notification_enabled'] else 'выключены'}")
    else:
        await query.edit_message_text("Ошибка")

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    status = "🟢 ВКЛЮЧЕНЫ" if data["enabled"] else "🔴 ВЫКЛЮЧЕНЫ"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{'🔴' if data['enabled'] else '🟢'} {'ВЫКЛЮЧИТЬ' if data['enabled'] else 'ВКЛЮЧИТЬ'}", callback_data="toggle_global")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="users_list")],
        [InlineKeyboardButton("◀️ Назад", callback_data="main_menu")]
    ])
    
    await query.edit_message_text(f"⚙️ *Настройки*\n\nУведомления: {status}\nПользователей: {len(data.get('users', []))}", reply_markup=kb, parse_mode="Markdown")

async def toggle_global(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data["enabled"] = not data["enabled"]
    save_data(data)
    
    if data["enabled"]:
        setup_schedule()
        await query.edit_message_text("✅ Уведомления ВКЛЮЧЕНЫ")
    else:
        clear_schedule()
        await query.edit_message_text("❌ Уведомления ВЫКЛЮЧЕНЫ")
    
    await asyncio.sleep(2)
    await settings_menu(update, context)

async def users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = "👥 *Пользователи:*\n\n"
    if data.get("users"):
        for uid in data["users"]:
            text += f"• ID: `{uid}`\n"
    else:
        text += "Нет пользователей"
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="settings")]])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = f"📊 *Статус*\n\n"
    text += f"🟢 Уведомления: {'Включены' if data['enabled'] else 'Выключены'}\n"
    text += f"📅 Событий: {len(data['events'])}\n"
    text += f"👥 Пользователей: {len(data.get('users', []))}\n\n"
    text += f"*Активные уведомления:*\n"
    
    enabled_count = len([e for e in data['events'] if e.get('notification_enabled', True)])
    text += f"🔔 {enabled_count} из {len(data['events'])} событий"
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="main_menu")]])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Распорядок", callback_data="show_schedule")],
        [InlineKeyboardButton("✏️ Редактировать", callback_data="edit_menu")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton("📊 Статус", callback_data="status")]
    ])
    await query.edit_message_text("🤖 *Бот распорядка дня*\n\nВыберите действие:", reply_markup=kb, parse_mode="Markdown")

def main():
    global bot
    app = Application.builder().token(TOKEN).build()
    bot = app.bot
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", lambda u,c: None))
    
    # Callback кнопки
    app.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(show_schedule, pattern="^show_schedule$"))
    app.add_handler(CallbackQueryHandler(edit_menu, pattern="^edit_menu$"))
    app.add_handler(CallbackQueryHandler(settings_menu, pattern="^settings$"))
    app.add_handler(CallbackQueryHandler(status, pattern="^status$"))
    app.add_handler(CallbackQueryHandler(toggle_global, pattern="^toggle_global$"))
    app.add_handler(CallbackQueryHandler(users_list, pattern="^users_list$"))
    app.add_handler(CallbackQueryHandler(list_events_for_edit, pattern="^list_edit_events$"))
    app.add_handler(CallbackQueryHandler(list_events_for_edit, pattern="^list_delete_events$"))
    app.add_handler(CallbackQueryHandler(edit_event_form, pattern="^edit_event_\\d+$"))
    app.add_handler(CallbackQueryHandler(delete_event_confirm, pattern="^delete_event_\\d+$"))
    app.add_handler(CallbackQueryHandler(confirm_delete, pattern="^confirm_del_\\d+$"))
    app.add_handler(CallbackQueryHandler(toggle_event_notification, pattern="^toggle_notif_\\d+$"))
    app.add_handler(CallbackQueryHandler(add_event_prompt, pattern="^add_event$"))
    
    # Обработчики редактирования полей (упрощённо)
    app.add_handler(CallbackQueryHandler(lambda u,c: u.answer(), pattern="^edit_title_"))
    app.add_handler(CallbackQueryHandler(lambda u,c: u.answer(), pattern="^edit_start_"))
    app.add_handler(CallbackQueryHandler(lambda u,c: u.answer(), pattern="^edit_end_"))
    app.add_handler(CallbackQueryHandler(lambda u,c: u.answer(), pattern="^edit_before_"))
    
    # Обработчик добавления события
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_event))
    
    # Запуск планировщика
    setup_schedule()
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    print("Бот запущен...")
    app.run_polling()
