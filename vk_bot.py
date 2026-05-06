import asyncio
import json
import os
import re
import time
import threading
from datetime import datetime
from vk_api import VkApi
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardButton

TOKEN = os.getenv("VK_TOKEN")
ADMIN_IDS = [int(os.getenv("ADMIN_ID"))] if os.getenv("ADMIN_ID") else []

DATA_DIR = "vk_user_data"
os.makedirs(DATA_DIR, exist_ok=True)

def parse_time(time_str):
    """Умный парсинг времени: 1430 -> 14:30"""
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

vk_api = None
user_schedules = {}

def clear_user_schedule(user_id):
    if user_id in user_schedules:
        for job in user_schedules[user_id]:
            job.cancel()
        user_schedules[user_id] = []

def format_time_to_seconds(time_str):
    """Преобразует HH:MM в секунды от полуночи"""
    hours, minutes = map(int, time_str.split(':'))
    return hours * 3600 + minutes * 60

def setup_user_schedule(user_id, user_data):
    clear_user_schedule(user_id)
    if not user_data.get("enabled", True):
        return
    
    jobs = []
    now_seconds = time.time()
    now_time_seconds = (now_seconds % 86400)
    
    for event in user_data["events"]:
        if not event.get("notification_enabled", True):
            continue
        
        event_seconds = format_time_to_seconds(event["time_start"])
        before_seconds = event.get("notification_minutes_before", 0) * 60
        send_seconds = event_seconds - before_seconds
        
        if send_seconds < 0:
            send_seconds += 86400
        
        # Время отправки сегодня или завтра
        delay = send_seconds - now_time_seconds
        if delay < 0:
            delay += 86400
        
        # Создаём таймер
        timer = threading.Timer(delay, lambda e=event, uid=user_id: asyncio.run_coroutine_threadsafe(send_notification(uid, e), asyncio.get_event_loop()))
        timer.daemon = True
        timer.start()
        jobs.append(timer)
    
    user_schedules[user_id] = jobs

async def send_notification(user_id, event):
    try:
        before = event.get("notification_minutes_before", 0)
        before_text = f" (за {before} мин)" if before > 0 else ""
        text = f"🔔 {event['title']}{before_text}\n⏰ {event['time_start']} - {event['time_end']}\n📝 Не забудьте!"
        vk_api.messages.send(
            peer_id=user_id,
            message=text,
            random_id=0
        )
    except Exception as e:
        print(f"Ошибка отправки: {e}")

def get_main_keyboard():
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("📅 Распорядок", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("⚙️ Настройки", color=VkKeyboardColor.SECONDARY)
    return keyboard

def get_schedule_keyboard():
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("✏️ Редактировать", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("➕ Добавить событие", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("⚙️ Настройки", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("🏠 Главное меню", color=VkKeyboardColor.SECONDARY)
    return keyboard

def get_edit_keyboard():
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("✏️ Редактировать событие", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("🗑️ Удалить событие", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("◀️ Назад", color=VkKeyboardColor.SECONDARY)
    return keyboard

def get_cancel_keyboard():
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("❌ Отмена", color=VkKeyboardColor.NEGATIVE)
    return keyboard

class UserState:
    def __init__(self):
        self.waiting_for = None  # 'title', 'start', 'end', 'before', 'user_id'
        self.temp_data = {}
        self.editing_event_id = None

user_states = {}

def get_state(user_id):
    if user_id not in user_states:
        user_states[user_id] = UserState()
    return user_states[user_id]

def clear_state(user_id):
    if user_id in user_states:
        user_states[user_id] = UserState()

def send_message(user_id, text, keyboard=None):
    try:
        vk_api.messages.send(
            peer_id=user_id,
            message=text,
            random_id=0,
            keyboard=keyboard.get_keyboard() if keyboard else None
        )
    except Exception as e:
        print(f"Ошибка отправки: {e}")

def process_message(event, user_id, text):
    if text and text.lower() == "/start":
        send_start_message(user_id)
        return
    
    state = get_state(user_id)
    
    # Обработка ожиданий ввода
    if state.waiting_for == "title":
        state.temp_data["new_title"] = text
        state.waiting_for = "start"
        send_message(user_id, "⏰ *Введите время начала*\n\nПоддерживаются форматы:\n• 14:30\n• 1430\n• 14.30\n• 14 30\n\nПример: 1430", get_cancel_keyboard())
        return
    
    if state.waiting_for == "start":
        parsed = parse_time(text)
        if parsed:
            state.temp_data["new_start"] = parsed
            state.waiting_for = "end"
            send_message(user_id, "⏰ *Введите время окончания*\n\nПоддерживаются форматы:\n• 15:30\n• 1530\n• 15.30\n• 15 30", get_cancel_keyboard())
        else:
            send_message(user_id, "❌ Не удалось распознать время. Попробуйте ещё раз (например: 1430 или 14:30):", get_cancel_keyboard())
        return
    
    if state.waiting_for == "end":
        parsed = parse_time(text)
        if parsed:
            state.temp_data["new_end"] = parsed
            # Показать выбор задержки
            keyboard = VkKeyboard(one_time=False)
            keyboard.add_button("0 мин (точно)", color=VkKeyboardColor.PRIMARY)
            keyboard.add_button("5 мин", color=VkKeyboardColor.PRIMARY)
            keyboard.add_line()
            keyboard.add_button("10 мин", color=VkKeyboardColor.PRIMARY)
            keyboard.add_button("15 мин", color=VkKeyboardColor.PRIMARY)
            keyboard.add_button("30 мин", color=VkKeyboardColor.PRIMARY)
            keyboard.add_line()
            keyboard.add_button("❌ Отмена", color=VkKeyboardColor.NEGATIVE)
            send_message(user_id, "🔔 *За сколько минут прислать уведомление?*", keyboard)
            state.waiting_for = "before"
        else:
            send_message(user_id, "❌ Не удалось распознать время. Попробуйте ещё раз:", get_cancel_keyboard())
        return
    
    if state.waiting_for == "before":
        if text in ["0 мин (точно)", "5 мин", "10 мин", "15 мин", "30 мин"]:
            before = int(text.split()[0])
            user_data = load_user_data(user_id)
            new_id = user_data["next_id"]
            user_data["next_id"] += 1
            
            new_event = {
                "id": new_id,
                "title": state.temp_data["new_title"],
                "time_start": state.temp_data["new_start"],
                "time_end": state.temp_data["new_end"],
                "notification_enabled": True,
                "notification_minutes_before": before
            }
            user_data["events"].append(new_event)
            save_user_data(user_id, user_data)
            clear_state(user_id)
            setup_user_schedule(user_id, user_data)
            send_message(user_id, f"✅ Событие \"{new_event['title']}\" добавлено!\n⏰ {new_event['time_start']} - {new_event['time_end']}\n🔔 Уведомление за {before} мин", get_main_keyboard())
        else:
            send_message(user_id, "Пожалуйста, выберите из предложенных вариантов.")
        return
    
    if state.waiting_for == "edit_title":
        user_data = load_user_data(user_id)
        event_id = state.editing_event_id
        for e in user_data["events"]:
            if e["id"] == event_id:
                e["title"] = text
                break
        save_user_data(user_id, user_data)
        clear_state(user_id)
        send_message(user_id, f"✅ Название изменено на: {text}")
        send_edit_menu(user_id, event_id)
        return
    
    if state.waiting_for == "edit_start":
        parsed = parse_time(text)
        if parsed:
            user_data = load_user_data(user_id)
            event_id = state.editing_event_id
            for e in user_data["events"]:
                if e["id"] == event_id:
                    e["time_start"] = parsed
                    break
            save_user_data(user_id, user_data)
            clear_state(user_id)
            setup_user_schedule(user_id, user_data)
            send_message(user_id, f"✅ Время начала изменено на: {parsed}")
            send_edit_menu(user_id, event_id)
        else:
            send_message(user_id, "❌ Неверный формат. Попробуйте ещё раз (например: 1430):", get_cancel_keyboard())
        return
    
    if state.waiting_for == "edit_end":
        parsed = parse_time(text)
        if parsed:
            user_data = load_user_data(user_id)
            event_id = state.editing_event_id
            for e in user_data["events"]:
                if e["id"] == event_id:
                    e["time_end"] = parsed
                    break
            save_user_data(user_id, user_data)
            clear_state(user_id)
            setup_user_schedule(user_id, user_data)
            send_message(user_id, f"✅ Время окончания изменено на: {parsed}")
            send_edit_menu(user_id, event_id)
        else:
            send_message(user_id, "❌ Неверный формат. Попробуйте ещё раз (например: 1530):", get_cancel_keyboard())
        return
    
    if state.waiting_for == "add_user":
        if user_id in ADMIN_IDS:
            try:
                new_user_id = int(text.strip())
                user_data = load_user_data(new_user_id)
                save_user_data(new_user_id, user_data)
                setup_user_schedule(new_user_id, user_data)
                send_message(user_id, f"✅ Пользователь {new_user_id} добавлен!")
            except:
                send_message(user_id, "❌ Неверный ID")
            clear_state(user_id)
            send_settings_menu(user_id)
        return

def send_start_message(user_id):
    user_data = load_user_data(user_id)
    save_user_data(user_id, user_data)
    setup_user_schedule(user_id, user_data)
    send_message(user_id, "🤖 *Бот распорядка дня*\n\nВыберите действие:", get_main_keyboard())

def send_schedule(user_id):
    user_data = load_user_data(user_id)
    text = "📅 *РАСПОРЯДОК ДНЯ*\n\n"
    for e in user_data["events"]:
        icon = "🔔" if e.get("notification_enabled", True) else "🔕"
        before = e.get("notification_minutes_before", 0)
        before_text = f" (за {before} мин)" if before > 0 else ""
        text += f"{icon} *{e['title']}*\n   ⏰ {e['time_start']} - {e['time_end']}{before_text}\n\n"
    send_message(user_id, text, get_schedule_keyboard())

def send_edit_choice(user_id):
    send_message(user_id, "Выберите действие:", get_edit_keyboard())

def send_events_list(user_id, action):
    user_data = load_user_data(user_id)
    if not user_data["events"]:
        send_message(user_id, "📭 Нет событий для редактирования", get_edit_keyboard())
        return
    
    keyboard = VkKeyboard(one_time=False)
    for event in user_data["events"]:
        keyboard.add_button(f"{event['time_start']} - {event['title'][:30]}", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
    keyboard.add_line()
    keyboard.add_button("❌ Отмена", color=VkKeyboardColor.NEGATIVE)
    
    send_message(user_id, f"{'✏️ Выберите событие для редактирования:' if action == 'edit' else '🗑️ Выберите событие для удаления:'}", keyboard)
    return user_data["events"]

def send_edit_menu(user_id, event_id):
    user_data = load_user_data(user_id)
    event = next((e for e in user_data["events"] if e["id"] == event_id), None)
    if not event:
        send_message(user_id, "❌ Событие не найдено")
        return
    
    status = "✅ Вкл" if event.get("notification_enabled", True) else "❌ Выкл"
    before_text = f"за {event.get('notification_minutes_before', 0)} мин" if event.get('notification_minutes_before', 0) > 0 else "точно в время"
    
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("📝 Изменить название", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("⏰ Изменить время начала", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("⏰ Изменить время окончания", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("🔔 Уведомление за (мин)", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button(f"🔔 Уведомления: {status}", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("◀️ Назад", color=VkKeyboardColor.SECONDARY)
    
    text = f"*✏️ Редактирование:*\n\n"
    text += f"📝 *Название:* {event['title']}\n"
    text += f"⏰ *Время:* {event['time_start']} - {event['time_end']}\n"
    text += f"🔔 *Уведомление:* {before_text}\n"
    text += f"📢 *Статус:* {status}"
    
    send_message(user_id, text, keyboard)

def delete_event(user_id, event_id):
    user_data = load_user_data(user_id)
    event = next((e for e in user_data["events"] if e["id"] == event_id), None)
    if event:
        user_data["events"] = [e for e in user_data["events"] if e["id"] != event_id]
        save_user_data(user_id, user_data)
        setup_user_schedule(user_id, user_data)
        send_message(user_id, f"✅ Событие \"{event['title']}\" удалено")
        send_schedule(user_id)
    else:
        send_message(user_id, "❌ Ошибка: событие не найдено")

def send_settings_menu(user_id):
    user_data = load_user_data(user_id)
    status = "🟢 ВКЛЮЧЕНЫ" if user_data["enabled"] else "🔴 ВЫКЛЮЧЕНЫ"
    
    keyboard = VkKeyboard(one_time=False)
    if user_data["enabled"]:
        keyboard.add_button("🔴 ВЫКЛЮЧИТЬ ВСЕ", color=VkKeyboardColor.NEGATIVE)
    else:
        keyboard.add_button("🟢 ВКЛЮЧИТЬ ВСЕ", color=VkKeyboardColor.POSITIVE)
    
    if user_id in ADMIN_IDS:
        keyboard.add_line()
        keyboard.add_button("➕ Добавить пользователя", color=VkKeyboardColor.PRIMARY)
    
    keyboard.add_line()
    keyboard.add_button("◀️ Назад", color=VkKeyboardColor.SECONDARY)
    
    send_message(user_id, f"⚙️ *НАСТРОЙКИ*\n\nУведомления: {status}\n\n*Примечание:* Для каждого события можно отдельно включить/выключить уведомления в режиме редактирования.", keyboard)

def toggle_global_notifications(user_id):
    user_data = load_user_data(user_id)
    user_data["enabled"] = not user_data["enabled"]
    save_user_data(user_id, user_data)
    
    if user_data["enabled"]:
        setup_user_schedule(user_id, user_data)
        send_message(user_id, "✅ Уведомления ВКЛЮЧЕНЫ")
    else:
        clear_user_schedule(user_id)
        send_message(user_id, "❌ Уведомления ВЫКЛЮЧЕНЫ")
    send_settings_menu(user_id)

def toggle_event_notification(user_id, event_id):
    user_data = load_user_data(user_id)
    for e in user_data["events"]:
        if e["id"] == event_id:
            e["notification_enabled"] = not e.get("notification_enabled", True)
            break
    save_user_data(user_id, user_data)
    setup_user_schedule(user_id, user_data)
    send_message(user_id, f"✅ Уведомления для события переключены")
    send_edit_menu(user_id, event_id)

def set_notification_before(user_id, event_id, before):
    user_data = load_user_data(user_id)
    for e in user_data["events"]:
        if e["id"] == event_id:
            e["notification_minutes_before"] = before
            break
    save_user_data(user_id, user_data)
    setup_user_schedule(user_id, user_data)
    send_message(user_id, f"✅ Уведомление настроено: {'точно в время' if before == 0 else f'за {before} мин'}")
    send_edit_menu(user_id, event_id)

def handle_button(user_id, payload):
    # Главное меню
    if payload == "📅 Распорядок":
        send_schedule(user_id)
        return
    
    if payload == "⚙️ Настройки":
        send_settings_menu(user_id)
        return
    
    if payload == "🏠 Главное меню":
        send_start_message(user_id)
        return
    
    # Меню редактирования
    if payload == "✏️ Редактировать":
        send_edit_choice(user_id)
        return
    
    if payload == "➕ Добавить событие":
        state = get_state(user_id)
        state.waiting_for = "title"
        state.temp_data = {}
        send_message(user_id, "📝 *Добавление события*\n\nВведите НАЗВАНИЕ события:", get_cancel_keyboard())
        return
    
    if payload == "✏️ Редактировать событие":
        events = send_events_list(user_id, "edit")
        state = get_state(user_id)
        state.waiting_for = "select_edit"
        return
    
    if payload == "🗑️ Удалить событие":
        events = send_events_list(user_id, "delete")
        state = get_state(user_id)
        state.waiting_for = "select_delete"
        return
    
    if payload == "◀️ Назад":
        send_schedule(user_id)
        return
    
    # Настройки
    if payload in ["🔴 ВЫКЛЮЧИТЬ ВСЕ", "🟢 ВКЛЮЧИТЬ ВСЕ"]:
        toggle_global_notifications(user_id)
        return
    
    if payload == "➕ Добавить пользователя":
        if user_id in ADMIN_IDS:
            state = get_state(user_id)
            state.waiting_for = "add_user"
            kb = VkKeyboard(one_time=False)
            kb.add_button("❌ Отмена", color=VkKeyboardColor.NEGATIVE)
            send_message(user_id, "📝 *Добавление пользователя*\n\nВведите Telegram ID пользователя (число):\n\nУзнать ID можно у @userinfobot", kb)
        return
    
    # Редактирование конкретного события
    if payload == "📝 Изменить название":
        send_message(user_id, "📝 Введите новое название события:", get_cancel_keyboard())
        return
    
    if payload == "⏰ Изменить время начала":
        send_message(user_id, "⏰ *Введите новое время начала*\n\nПоддерживаются форматы:\n• 14:30\n• 1430\n• 14.30\n• 14 30", get_cancel_keyboard())
        return
    
    if payload == "⏰ Изменить время окончания":
        send_message(user_id, "⏰ *Введите новое время окончания*\n\nПоддерживаются форматы:\n• 15:30\n• 1530\n• 15.30\n• 15 30", get_cancel_keyboard())
        return
    
    if payload == "🔔 Уведомление за (мин)":
        kb = VkKeyboard(one_time=False)
        kb.add_button("0 мин (точно)", color=VkKeyboardColor.PRIMARY)
        kb.add_button("5 мин", color=VkKeyboardColor.PRIMARY)
        kb.add_line()
        kb.add_button("10 мин", color=VkKeyboardColor.PRIMARY)
        kb.add_button("15 мин", color=VkKeyboardColor.PRIMARY)
        kb.add_button("30 мин", color=VkKeyboardColor.PRIMARY)
        kb.add_line()
        kb.add_button("◀️ Назад", color=VkKeyboardColor.SECONDARY)
        send_message(user_id, "🔔 Выберите за сколько минут присылать уведомление:", kb)
        return
    
    if payload.startswith("🔔 Уведомления:"):
        state = get_state(user_id)
        if state.editing_event_id:
            toggle_event_notification(user_id, state.editing_event_id)
        return
    
    if payload == "❌ Отмена":
        clear_state(user_id)
        send_start_message(user_id)
        return

def main():
    global vk_api
    vk_session = VkApi(token=TOKEN)
    vk_api = vk_session.get_api()
    longpoll = VkBotLongPoll(vk_session, int(os.getenv("VK_GROUP_ID")))
    
    print("✅ ВК Бот запущен!")
    
    for event in longpoll.listen():
        if event.type == VkBotEventType.MESSAGE_NEW:
            try:
                msg = event.object.message
                user_id = msg['from_id']
                text = msg.get('text', '')
                payload = msg.get('payload')
                
                # Обработка кнопок
                if payload:
                    handle_button(user_id, payload)
                elif text:
                    process_message(event, user_id, text)
                    
            except Exception as e:
                print(f"Ошибка обработки: {e}")
                import traceback
                traceback.print_exc()

if __name__ == "__main__":
    main()