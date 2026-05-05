import asyncio
import json
import os
import re
from datetime import datetime
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters, ConversationHandler
import schedule
import threading
import time

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(os.getenv("ADMIN_ID"))]

DATA_DIR = "user_data"
os.makedirs(DATA_DIR, exist_ok=True)

# Состояния для ConversationHandler
WAITING_TITLE, WAITING_START, WAITING_END, WAITING_BEFORE = range(4)
EDITING_TITLE, EDITING_START, EDITING_END, EDITING_BEFORE = range(4, 8)
WAITING_USER_ID = 8

def parse_time(time_str):
    digits = re.sub(r'\D', '', time_str)
    if not digits:
        return None
    if len(digits) == 1 or len(digits) == 2:
        return None
    if len(digits) == 3:
        digits = '0' + digits
    if len(digits) >= 4:
        digits = digits[:4]
    if len(digits) == 4:
        hours = int(digits[:2])
        minutes = int(digits[2:])
        if 0 <= hours <= 23 and 0 <= minutes <= 59:
            return f"{hours:02d}:{minutes:02d}"
    return None

def get_user_file(user_id):
    return os.path.join(DATA_DIR, f"user_{user_id}.json")

def load_user_data(user_id):
    file_path = get_user_file(user_id)
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    # Новый пользователь — дефолтное расписание
    return {
        "enabled": True,
        "events": [
            {"id": 1, "time_start": "06:30", "time_end": "06:35", "title": "🌅 Подъём", "notification_enabled": True, "notification_minutes_before": 0},
            {"id": 2, "time_start": "06:35", "time_end": "06:50", "title": "📓 Утренний дневник", "notification_enabled": True, "notification_minutes_before": 0},
            {"id": 3, "time_start": "07:00", "time_end": "07:30", "title": "🍳 Завтрак", "notification_enabled": True, "notification_minutes_before": 5},
            {"id": 4, "time_start": "07:30", "time_end": "08:00", "title": "🚗 Отвезти дочку", "notification_enabled": True, "notification_minutes_before": 5},
            {"id": 5, "time_start": "08:00", "time_end": "09:00", "title": "🏊 Бассейн", "notification_enabled": True, "notification_minutes_before": 10},
            {"id": 6, "time_start": "09:30", "time_end": "11:00", "title": "📈 Торговля 1", "notification_enabled": True, "notification_minutes_before": 5},
            {"id": 7, "time_start": "11:15", "time_end": "12:45", "title": "📉 Торговля 2", "notification_enabled": True, "notification_minutes_before": 5},
            {"id": 8, "time_start": "13:00", "time_end": "13:30", "title": "🍽️ Обед", "notification_enabled": True, "notification_minutes_before": 5},
            {"id": 9, "time_start": "14:00", "time_end": "15:00", "title": "🧹 Уборка", "notification_enabled": True, "notification_minutes_before": 5},
            {"id": 10, "time_start": "15:00", "time_end": "16:00", "title": "📖 Чтение", "notification_enabled": True, "notification_minutes_before": 5},
            {"id": 11, "time_start": "16:30", "time_end": "17:30", "title": "🥋 Кружок кудо", "notification_enabled": True, "notification_minutes_before": 10},
            {"id": 12, "time_start": "18:00", "time_end": "18:30", "title": "🍲 Ужин", "notification_enabled": True, "notification_minutes_before": 5},
            {"id": 13, "time_start": "19:00", "time_end": "20:00", "title": "🎮 Отдых", "notification_enabled": True, "notification_minutes_before": 5},
            {"id": 14, "time_start": "20:00", "time_end": "20:30", "title": "📘 Вечерний дневник", "notification_enabled": True, "notification_minutes_before": 5},
            {"id": 15, "time_start": "22:00", "time_end": "22:00", "title": "💤 Отбой", "notification_enabled": True, "notification_minutes_before": 15}
        ],
        "next_id": 16
    }

def save_user_data(user_id, data):
    with open(get_user_file(user_id), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

bot = None
user_schedules = {}  # user_id: {scheduled_jobs}

def clear_user_schedule(user_id):
    if user_id in user_schedules:
        for job in user_schedules[user_id]:
            schedule.cancel_job(job)
        user_schedules[user_id] = []

def setup_user_schedule(user_id, user_data):
    clear_user_schedule(user_id)
    if not user_data.get("enabled", True):
        return
    
    jobs = []
    for event in user_data["events"]:
        if not event.get("notification_enabled", True):
            continue
        hour, minute = map(int, event["time_start"].split(':'))
        before = event.get("notification_minutes_before", 0)
        send_minute = minute - before
        send_hour = hour
        if send_minute < 0:
            send_hour -= 1
            send_minute += 60
            if send_hour < 0:
                send_hour = 23
        send_time = f"{send_hour:02d}:{send_minute:02d}"
        job = schedule.every().day.at(send_time).do(
            lambda e=event, uid=user_id: asyncio.run_coroutine_threadsafe(send_notification(uid, e), asyncio.get_event_loop())
        )
        jobs.append(job)
    user_schedules[user_id] = jobs

async def send_notification(user_id, event):
    try:
        before = event.get("notification_minutes_before", 0)
        before_text = f" (за {before} мин)" if before > 0 else ""
        text = f"🔔 {event['title']}{before_text}\n⏰ {event['time_start']} - {event['time_end']}\n📝 Не забудьте!"
        await bot.send_message(chat_id=user_id, text=text)
    except:
        pass

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Загружаем или создаём данные пользователя
    user_data = load_user_data(user_id)
    save_user_data(user_id, user_data)
    setup_user_schedule(user_id, user_data)
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Распорядок", callback_data="show_schedule")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")]
    ])
    await update.message.reply_text("🤖 *Бот распорядка дня*\n\nВыберите действие:", reply_markup=kb, parse_mode="Markdown")

async def show_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user_data = load_user_data(user_id)
    
    text = "📅 *РАСПОРЯДОК ДНЯ*\n\n"
    for e in user_data["events"]:
        icon = "🔔" if e.get("notification_enabled", True) else "🔕"
        before = e.get("notification_minutes_before", 0)
        before_text = f" (за {before} мин)" if before > 0 else ""
        text += f"{icon} *{e['title']}*\n   ⏰ {e['time_start']} - {e['time_end']}{before_text}\n\n"
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Редактировать", callback_data="edit_choice")],
        [InlineKeyboardButton("➕ Добавить событие", callback_data="add_event")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

async def edit_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Редактировать событие", callback_data="edit_event_list")],
        [InlineKeyboardButton("🗑️ Удалить событие", callback_data="delete_event_list")],
        [InlineKeyboardButton("◀️ Назад", callback_data="show_schedule")]
    ])
    await query.edit_message_text("Выберите действие:", reply_markup=kb)

async def list_events_for_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user_data = load_user_data(user_id)
    action = query.data.split("_")[0]
    
    buttons = []
    for event in user_data["events"]:
        buttons.append([InlineKeyboardButton(f"{event['time_start']} - {event['title'][:30]}", callback_data=f"{action}_event_{event['id']}")])
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="edit_choice")])
    kb = InlineKeyboardMarkup(buttons)
    text = "✏️ Выберите событие для редактирования:" if action == "edit" else "🗑️ Выберите событие для удаления:"
    await query.edit_message_text(text, reply_markup=kb)

async def edit_event_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user_data = load_user_data(user_id)
    event_id = int(query.data.split("_")[2])
    event = next((e for e in user_data["events"] if e["id"] == event_id), None)
    
    if not event:
        await query.edit_message_text("❌ Событие не найдено")
        return
    
    context.user_data["editing_event_id"] = event_id
    
    status = "✅ Вкл" if event.get("notification_enabled", True) else "❌ Выкл"
    before_text = f"за {event.get('notification_minutes_before', 0)} мин" if event.get('notification_minutes_before', 0) > 0 else "точно в время"
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Изменить название", callback_data=f"edit_title_{event_id}")],
        [InlineKeyboardButton("⏰ Изменить время начала", callback_data=f"edit_start_{event_id}")],
        [InlineKeyboardButton("⏰ Изменить время окончания", callback_data=f"edit_end_{event_id}")],
        [InlineKeyboardButton("🔔 Уведомление за (мин)", callback_data=f"edit_before_{event_id}")],
        [InlineKeyboardButton(f"🔔 Уведомления: {status}", callback_data=f"toggle_notif_{event_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="edit_choice")]
    ])
    
    text = f"*✏️ Редактирование:*\n\n"
    text += f"📝 *Название:* {event['title']}\n"
    text += f"⏰ *Время:* {event['time_start']} - {event['time_end']}\n"
    text += f"🔔 *Уведомление:* {before_text}\n"
    text += f"📢 *Статус:* {status}"
    
    await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

async def delete_event_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user_data = load_user_data(user_id)
    event_id = int(query.data.split("_")[2])
    event = next((e for e in user_data["events"] if e["id"] == event_id), None)
    
    if not event:
        await query.edit_message_text("❌ Событие не найдено")
        return
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_del_{event_id}")],
        [InlineKeyboardButton("❌ Нет", callback_data="edit_choice")]
    ])
    await query.edit_message_text(f"🗑️ Удалить событие \"{event['title']}\"?", reply_markup=kb)

async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user_data = load_user_data(user_id)
    event_id = int(query.data.split("_")[2])
    
    user_data["events"] = [e for e in user_data["events"] if e["id"] != event_id]
    save_user_data(user_id, user_data)
    setup_user_schedule(user_id, user_data)
    
    await query.edit_message_text(f"✅ Событие удалено")
    # Показываем распорядок
    await show_schedule(update, context)

async def add_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="show_schedule")]])
    await query.edit_message_text("📝 *Добавление события*\n\nВведите НАЗВАНИЕ события:", reply_markup=kb, parse_mode="Markdown")
    return WAITING_TITLE

async def add_event_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_title"] = update.message.text
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="show_schedule")]])
    await update.message.reply_text("⏰ *Введите время начала*\n\nПоддерживаются форматы:\n• 14:30\n• 1430\n• 14.30\n• 14 30\n\nПример: 1430", reply_markup=kb, parse_mode="Markdown")
    return WAITING_START

async def add_event_start_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_str = update.message.text.strip()
    parsed_time = parse_time(time_str)
    
    if parsed_time:
        context.user_data["new_start"] = parsed_time
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="show_schedule")]])
        await update.message.reply_text("⏰ *Введите время окончания*\n\nПоддерживаются форматы:\n• 15:30\n• 1530\n• 15.30\n• 15 30\n\nПример: 1530", reply_markup=kb, parse_mode="Markdown")
        return WAITING_END
    else:
        await update.message.reply_text("❌ Не удалось распознать время.\n\nПожалуйста, введите время в одном из форматов:\n• 14:30\n• 1430\n• 14.30\n• 14 30")
        return WAITING_START

async def add_event_end_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_str = update.message.text.strip()
    parsed_time = parse_time(time_str)
    
    if parsed_time:
        context.user_data["new_end"] = parsed_time
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("0 мин (точно)", callback_data="before_0")],
            [InlineKeyboardButton("5 мин", callback_data="before_5")],
            [InlineKeyboardButton("10 мин", callback_data="before_10")],
            [InlineKeyboardButton("15 мин", callback_data="before_15")],
            [InlineKeyboardButton("30 мин", callback_data="before_30")],
            [InlineKeyboardButton("◀️ Отмена", callback_data="show_schedule")]
        ])
        await update.message.reply_text("🔔 *За сколько минут прислать уведомление?*", reply_markup=kb, parse_mode="Markdown")
        return WAITING_BEFORE
    else:
        await update.message.reply_text("❌ Не удалось распознать время.\n\nПожалуйста, введите время в одном из форматов:\n• 15:30\n• 1530\n• 15.30\n• 15 30")
        return WAITING_END

async def add_event_before(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user_data = load_user_data(user_id)
    
    before = int(query.data.split("_")[1])
    
    new_id = user_data["next_id"]
    user_data["next_id"] += 1
    
    new_event = {
        "id": new_id,
        "title": context.user_data["new_title"],
        "time_start": context.user_data["new_start"],
        "time_end": context.user_data["new_end"],
        "notification_enabled": True,
        "notification_minutes_before": before
    }
    
    user_data["events"].append(new_event)
    save_user_data(user_id, user_data)
    setup_user_schedule(user_id, user_data)
    
    await query.edit_message_text(f"✅ Событие \"{new_event['title']}\" добавлено!")
    await show_schedule(update, context)
    return ConversationHandler.END

async def edit_title_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split("_")[2])
    context.user_data["editing_event_id"] = event_id
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="edit_choice")]])
    await query.edit_message_text("📝 Введите новое название события:", reply_markup=kb)
    return EDITING_TITLE

async def edit_title_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = load_user_data(user_id)
    event_id = context.user_data["editing_event_id"]
    event = next((e for e in user_data["events"] if e["id"] == event_id), None)
    
    if event:
        event["title"] = update.message.text
        save_user_data(user_id, user_data)
        await update.message.reply_text(f"✅ Название изменено на: {event['title']}")
    else:
        await update.message.reply_text("❌ Ошибка")
    await edit_event_menu(update, context)
    return ConversationHandler.END

async def edit_start_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split("_")[2])
    context.user_data["editing_event_id"] = event_id
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="edit_choice")]])
    await query.edit_message_text("⏰ *Введите новое время начала*\n\nПоддерживаются форматы:\n• 14:30\n• 1430\n• 14.30\n• 14 30", reply_markup=kb, parse_mode="Markdown")
    return EDITING_START

async def edit_start_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = load_user_data(user_id)
    time_str = update.message.text.strip()
    parsed_time = parse_time(time_str)
    
    if parsed_time:
        event_id = context.user_data["editing_event_id"]
        event = next((e for e in user_data["events"] if e["id"] == event_id), None)
        if event:
            event["time_start"] = parsed_time
            save_user_data(user_id, user_data)
            setup_user_schedule(user_id, user_data)
            await update.message.reply_text(f"✅ Время начала изменено на: {event['time_start']}")
        else:
            await update.message.reply_text("❌ Ошибка")
        await edit_event_menu(update, context)
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ Не удалось распознать время")
        return EDITING_START

async def edit_end_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split("_")[2])
    context.user_data["editing_event_id"] = event_id
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="edit_choice")]])
    await query.edit_message_text("⏰ *Введите новое время окончания*\n\nПоддерживаются форматы:\n• 15:30\n• 1530\n• 15.30\n• 15 30", reply_markup=kb, parse_mode="Markdown")
    return EDITING_END

async def edit_end_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = load_user_data(user_id)
    time_str = update.message.text.strip()
    parsed_time = parse_time(time_str)
    
    if parsed_time:
        event_id = context.user_data["editing_event_id"]
        event = next((e for e in user_data["events"] if e["id"] == event_id), None)
        if event:
            event["time_end"] = parsed_time
            save_user_data(user_id, user_data)
            setup_user_schedule(user_id, user_data)
            await update.message.reply_text(f"✅ Время окончания изменено на: {event['time_end']}")
        else:
            await update.message.reply_text("❌ Ошибка")
        await edit_event_menu(update, context)
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ Не удалось распознать время")
        return EDITING_END

async def edit_before_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split("_")[2])
    context.user_data["editing_event_id"] = event_id
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("0 мин (точно)", callback_data=f"set_before_{event_id}_0")],
        [InlineKeyboardButton("5 мин", callback_data=f"set_before_{event_id}_5")],
        [InlineKeyboardButton("10 мин", callback_data=f"set_before_{event_id}_10")],
        [InlineKeyboardButton("15 мин", callback_data=f"set_before_{event_id}_15")],
        [InlineKeyboardButton("30 мин", callback_data=f"set_before_{event_id}_30")],
        [InlineKeyboardButton("◀️ Назад", callback_data=f"edit_event_{event_id}")]
    ])
    await query.edit_message_text("🔔 Выберите за сколько минут до события присылать уведомление:", reply_markup=kb)
    return EDITING_BEFORE

async def set_before_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user_data = load_user_data(user_id)
    
    parts = query.data.split("_")
    event_id = int(parts[2])
    before = int(parts[3])
    
    event = next((e for e in user_data["events"] if e["id"] == event_id), None)
    if event:
        event["notification_minutes_before"] = before
        save_user_data(user_id, user_data)
        setup_user_schedule(user_id, user_data)
        await query.edit_message_text(f"✅ Уведомление настроено: {'точно в время' if before == 0 else f'за {before} мин'}")
    else:
        await query.edit_message_text("❌ Ошибка")
    
    await edit_event_menu(update, context)
    return ConversationHandler.END

async def toggle_notification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user_data = load_user_data(user_id)
    event_id = int(query.data.split("_")[2])
    event = next((e for e in user_data["events"] if e["id"] == event_id), None)
    
    if event:
        event["notification_enabled"] = not event.get("notification_enabled", True)
        save_user_data(user_id, user_data)
        setup_user_schedule(user_id, user_data)
        status = "включены" if event["notification_enabled"] else "выключены"
        await query.edit_message_text(f"✅ Уведомления для \"{event['title']}\" {status}")
    else:
        await query.edit_message_text("❌ Ошибка")
    await edit_event_menu(update, context)

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user_data = load_user_data(user_id)
    
    status = "🟢 ВКЛЮЧЕНЫ" if user_data["enabled"] else "🔴 ВЫКЛЮЧЕНЫ"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{'🔴' if user_data['enabled'] else '🟢'} {'ВЫКЛЮЧИТЬ ВСЕ' if user_data['enabled'] else 'ВКЛЮЧИТЬ ВСЕ'}", callback_data="toggle_global")],
        [InlineKeyboardButton("◀️ Назад", callback_data="show_schedule")]
    ])
    
    # Добавляем кнопку добавления пользователя только для админа
    if user_id in ADMIN_IDS:
        kb.inline_keyboard.insert(1, [InlineKeyboardButton("➕ Добавить пользователя", callback_data="add_user_prompt")])
    
    await query.edit_message_text(f"⚙️ *НАСТРОЙКИ*\n\nУведомления: {status}\n\n*Примечание:* Для каждого события можно отдельно включить/выключить уведомления в режиме редактирования.", reply_markup=kb, parse_mode="Markdown")

async def add_user_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📝 *Добавление пользователя*\n\nВведите Telegram ID пользователя (число):\n\nУзнать ID можно у @userinfobot", parse_mode="Markdown")
    return WAITING_USER_ID

async def add_user_by_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет прав")
        return ConversationHandler.END
    
    try:
        new_user_id = int(update.message.text.strip())
        # Создаём файл пользователя с дефолтным расписанием
        user_data = load_user_data(new_user_id)
        save_user_data(new_user_id, user_data)
        setup_user_schedule(new_user_id, user_data)
        await update.message.reply_text(f"✅ Пользователь {new_user_id} добавлен! Он может написать боту /start")
    except:
        await update.message.reply_text("❌ Неверный ID. Введите число.")
        return WAITING_USER_ID
    
    await settings_menu(update, context)
    return ConversationHandler.END

async def toggle_global(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user_data = load_user_data(user_id)
    
    user_data["enabled"] = not user_data["enabled"]
    save_user_data(user_id, user_data)
    
    if user_data["enabled"]:
        setup_user_schedule(user_id, user_data)
        await query.edit_message_text("✅ Уведомления ВКЛЮЧЕНЫ")
    else:
        clear_user_schedule(user_id)
        await query.edit_message_text("❌ Уведомления ВЫКЛЮЧЕНЫ")
    
    await asyncio.sleep(1.5)
    await settings_menu(update, context)

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Распорядок", callback_data="show_schedule")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")]
    ])
    await query.edit_message_text("🤖 *Бот распорядка дня*\n\nВыберите действие:", reply_markup=kb, parse_mode="Markdown")

def main():
    global bot
    app = Application.builder().token(TOKEN).build()
    bot = app.bot
    
    # ConversationHandler для добавления события
    add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_event_start, pattern="^add_event$")],
        states={
            WAITING_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_event_title)],
            WAITING_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_event_start_time)],
            WAITING_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_event_end_time)],
            WAITING_BEFORE: [CallbackQueryHandler(add_event_before, pattern="^before_")]
        },
        fallbacks=[CallbackQueryHandler(lambda u,c: ConversationHandler.END, pattern="^show_schedule$")]
    )
    
    edit_title_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_title_start, pattern="^edit_title_")],
        states={EDITING_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_title_input)]},
        fallbacks=[CallbackQueryHandler(lambda u,c: ConversationHandler.END, pattern="^edit_choice$")]
    )
    
    edit_start_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_start_time, pattern="^edit_start_")],
        states={EDITING_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_start_input)]},
        fallbacks=[CallbackQueryHandler(lambda u,c: ConversationHandler.END, pattern="^edit_choice$")]
    )
    
    edit_end_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_end_time, pattern="^edit_end_")],
        states={EDITING_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_end_input)]},
        fallbacks=[CallbackQueryHandler(lambda u,c: ConversationHandler.END, pattern="^edit_choice$")]
    )
    
    edit_before_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_before_menu, pattern="^edit_before_")],
        states={EDITING_BEFORE: [CallbackQueryHandler(set_before_value, pattern="^set_before_")]},
        fallbacks=[CallbackQueryHandler(lambda u,c: ConversationHandler.END, pattern="^edit_choice$")]
    )
    
    add_user_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_user_prompt, pattern="^add_user_prompt$")],
        states={WAITING_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_user_by_id)]},
        fallbacks=[CommandHandler("cancel", lambda u,c: ConversationHandler.END)]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(add_conv)
    app.add_handler(edit_title_conv)
    app.add_handler(edit_start_conv)
    app.add_handler(edit_end_conv)
    app.add_handler(edit_before_conv)
    app.add_handler(add_user_conv)
    
    app.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(show_schedule, pattern="^show_schedule$"))
    app.add_handler(CallbackQueryHandler(edit_choice, pattern="^edit_choice$"))
    app.add_handler(CallbackQueryHandler(list_events_for_edit, pattern="^edit_event_list$"))
    app.add_handler(CallbackQueryHandler(list_events_for_edit, pattern="^delete_event_list$"))
    app.add_handler(CallbackQueryHandler(edit_event_menu, pattern="^edit_event_\\d+$"))
    app.add_handler(CallbackQueryHandler(delete_event_confirm, pattern="^delete_event_\\d+$"))
    app.add_handler(CallbackQueryHandler(confirm_delete, pattern="^confirm_del_\\d+$"))
    app.add_handler(CallbackQueryHandler(toggle_notification, pattern="^toggle_notif_\\d+$"))
    app.add_handler(CallbackQueryHandler(settings_menu, pattern="^settings$"))
    app.add_handler(CallbackQueryHandler(toggle_global, pattern="^toggle_global$"))
    
    # Запуск планировщика в отдельном потоке
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    print("✅ Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
