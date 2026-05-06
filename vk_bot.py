import asyncio
import json
import os
import re
import time
import threading
from datetime import datetime, timedelta
from vk_api import VkApi
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor

TOKEN = os.getenv("VK_TOKEN")
GROUP_ID = int(os.getenv("VK_GROUP_ID"))
ADMIN_IDS = [int(os.getenv("ADMIN_ID"))] if os.getenv("ADMIN_ID") else []

DATA_DIR = "vk_user_data"
os.makedirs(DATA_DIR, exist_ok=True)

# Функции для работы с данными пользователей
def get_user_file(user_id):
    return os.path.join(DATA_DIR, f"user_{user_id}.json")

def parse_time(time_str):
    digits = re.sub(r'\D', '', time_str)
    if not digits:
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

def load_user_data(user_id):
    file_path = get_user_file(user_id)
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "enabled": True,
        "events": [
            {"id": 1, "time_start": "06:30", "time_end": "06:35", "title": "🌅 Подъём", "notification_enabled": True, "notification_minutes_before": 0},
            {"id": 2, "time_start": "07:00", "time_end": "07:30", "title": "🍳 Завтрак", "notification_enabled": True, "notification_minutes_before": 5},
            {"id": 3, "time_start": "08:00", "time_end": "09:00", "title": "🏊 Бассейн", "notification_enabled": True, "notification_minutes_before": 10},
            {"id": 4, "time_start": "09:30", "time_end": "11:00", "title": "📈 Торговля 1", "notification_enabled": True, "notification_minutes_before": 5},
            {"id": 5, "time_start": "13:00", "time_end": "13:30", "title": "🍽️ Обед", "notification_enabled": True, "notification_minutes_before": 5},
            {"id": 6, "time_start": "15:00", "time_end": "16:00", "title": "📖 Чтение", "notification_enabled": True, "notification_minutes_before": 5},
            {"id": 7, "time_start": "18:00", "time_end": "18:30", "title": "🍲 Ужин", "notification_enabled": True, "notification_minutes_before": 5},
            {"id": 8, "time_start": "22:00", "time_end": "22:00", "title": "💤 Отбой", "notification_enabled": True, "notification_minutes_before": 15}
        ],
        "next_id": 9
    }

def save_user_data(user_id, data):
    with open(get_user_file(user_id), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# Планировщик уведомлений
user_schedules = {}

def schedule_user(user_id, user_data):
    """Запускает таймеры для всех событий пользователя"""
    if user_id in user_schedules:
        for timer in user_schedules[user_id]:
            timer.cancel()
    
    if not user_data.get("enabled", True):
        user_schedules[user_id] = []
        return
    
    now = datetime.now()
    timers = []
    
    for event in user_data["events"]:
        if not event.get("notification_enabled", True):
            continue
        
        event_time = datetime.strptime(event["time_start"], "%H:%M").time()
        event_datetime = datetime.combine(now.date(), event_time)
        
        before_min = event.get("notification_minutes_before", 0)
        send_datetime = event_datetime - timedelta(minutes=before_min)
        
        if send_datetime < now:
            send_datetime += timedelta(days=1)
        
        delay = (send_datetime - now).total_seconds()
        
        timer = threading.Timer(delay, send_notification, args=[user_id, event])
        timer.daemon = True
        timer.start()
        timers.append(timer)
    
    user_schedules[user_id] = timers

def send_notification(user_id, event):
    """Отправляет уведомление пользователю"""
    try:
        vk = VkApi(token=TOKEN)
        before = event.get("notification_minutes_before", 0)
        before_text = f" (за {before} мин)" if before > 0 else ""
        text = f"🔔 {event['title']}{before_text}\n⏰ {event['time_start']} - {event['time_end']}\n📝 Не забудьте!"
        vk.method("messages.send", {
            "peer_id": user_id,
            "message": text,
            "random_id": 0
        })
    except Exception as e:
        print(f"Ошибка отправки уведомления: {e}")

# Клавиатуры
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

def get_back_keyboard():
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("◀️ Назад", color=VkKeyboardColor.SECONDARY)
    return keyboard

def get_cancel_keyboard():
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("❌ Отмена", color=VkKeyboardColor.NEGATIVE)
    return keyboard

# Хранилище состояний пользователей
user_states = {}

def get_state(user_id):
    if user_id not in user_states:
        user_states[user_id] = {"step": None, "data": {}, "event_id": None}
    return user_states[user_id]

def clear_state(user_id):
    if user_id in user_states:
        user_states[user_id] = {"step": None, "data": {}, "event_id": None}

# Обработчики команд
def send_message(peer_id, text, keyboard=None):
    try:
        vk = VkApi(token=TOKEN)
        params = {
            "peer_id": peer_id,
            "message": text,
            "random_id": 0
        }
        if keyboard:
            params["keyboard"] = keyboard.get_keyboard()
        vk.method("messages.send", params)
    except Exception as e:
        print(f"Ошибка отправки: {e}")

def send_start(user_id):
    load_user_data(user_id)
    schedule_user(user_id, load_user_data(user_id))
    send_message(user_id, "🤖 *Бот распорядка дня*\n\nВыберите действие:", get_main_keyboard())

def show_schedule(user_id):
    data = load_user_data(user_id)
    text = "📅 *РАСПОРЯДОК ДНЯ*\n\n"
    for e in data["events"]:
        icon = "🔔" if e.get("notification_enabled", True) else "🔕"
        before = e.get("notification_minutes_before", 0)
        before_text = f" (за {before} мин)" if before > 0 else ""
        text += f"{icon} *{e['title']}*\n   ⏰ {e['time_start']} - {e['time_end']}{before_text}\n\n"
    send_message(user_id, text, get_schedule_keyboard())

def show_events_list(user_id, action):
    data = load_user_data(user_id)
    if not data["events"]:
        send_message(user_id, "📭 Нет событий", get_edit_keyboard())
        return
    
    keyboard = VkKeyboard(one_time=False)
    for e in data["events"]:
        keyboard.add_button(f"{e['time_start']} - {e['title'][:25]}", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
    keyboard.add_line()
    keyboard.add_button("❌ Отмена", color=VkKeyboardColor.NEGATIVE)
    
    state = get_state(user_id)
    state["step"] = f"select_{action}"
    
    send_message(user_id, f"{'✏️ Выберите событие' if action == 'edit' else '🗑️ Выберите событие для удаления'}:", keyboard)

def show_edit_menu(user_id, event_id):
    data = load_user_data(user_id)
    event = next((e for e in data["events"] if e["id"] == event_id), None)
    if not event:
        send_message(user_id, "❌ Событие не найдено")
        return
    
    state = get_state(user_id)
    state["event_id"] = event_id
    
    status = "✅ Вкл" if event.get("notification_enabled", True) else "❌ Выкл"
    before_text = f"за {event.get('notification_minutes_before', 0)} мин" if event.get('notification_minutes_before', 0) > 0 else "точно в время"
    
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("📝 Изменить название", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("⏰ Изменить время начала", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("⏰ Изменить время окончания", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("🔔 Уведомление за (мин)", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button(f"🔔 {status}", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("◀️ Назад", color=VkKeyboardColor.SECONDARY)
    
    text = f"*✏️ Редактирование:*\n\n📝 {event['title']}\n⏰ {event['time_start']} - {event['time_end']}\n🔔 {before_text}\n📢 {status}"
    send_message(user_id, text, keyboard)

def add_event_start(user_id):
    state = get_state(user_id)
    state["step"] = "add_title"
    state["data"] = {}
    send_message(user_id, "📝 *Добавление события*\n\nВведите НАЗВАНИЕ события:", get_cancel_keyboard())

def handle_text(user_id, text):
    state = get_state(user_id)
    step = state["step"]
    
    # Добавление события
    if step == "add_title":
        state["data"]["title"] = text
        state["step"] = "add_start"
        send_message(user_id, "⏰ *Введите время начала*\n\nФорматы: 14:30, 1430, 14.30, 14 30", get_cancel_keyboard())
    
    elif step == "add_start":
        parsed = parse_time(text)
        if parsed:
            state["data"]["start"] = parsed
            state["step"] = "add_end"
            send_message(user_id, "⏰ *Введите время окончания*\n\nФорматы: 15:30, 1530, 15.30, 15 30", get_cancel_keyboard())
        else:
            send_message(user_id, "❌ Не распознано. Попробуйте: 1430 или 14:30")
    
    elif step == "add_end":
        parsed = parse_time(text)
        if parsed:
            state["data"]["end"] = parsed
            state["step"] = "add_before"
            keyboard = VkKeyboard(one_time=False)
            keyboard.add_button("0 мин", color=VkKeyboardColor.PRIMARY)
            keyboard.add_button("5 мин", color=VkKeyboardColor.PRIMARY)
            keyboard.add_button("10 мин", color=VkKeyboardColor.PRIMARY)
            keyboard.add_button("15 мин", color=VkKeyboardColor.PRIMARY)
            keyboard.add_button("30 мин", color=VkKeyboardColor.PRIMARY)
            keyboard.add_line()
            keyboard.add_button("❌ Отмена", color=VkKeyboardColor.NEGATIVE)
            send_message(user_id, "🔔 *За сколько минут прислать уведомление?*", keyboard)
        else:
            send_message(user_id, "❌ Не распознано. Попробуйте: 1530 или 15:30")
    
    # Редактирование названия
    elif step == "edit_title":
        data = load_user_data(user_id)
        for e in data["events"]:
            if e["id"] == state["event_id"]:
                e["title"] = text
                break
        save_user_data(user_id, data)
        clear_state(user_id)
        send_message(user_id, f"✅ Название изменено на: {text}")
        show_edit_menu(user_id, state["event_id"])
    
    # Редактирование времени начала
    elif step == "edit_start":
        parsed = parse_time(text)
        if parsed:
            data = load_user_data(user_id)
            for e in data["events"]:
                if e["id"] == state["event_id"]:
                    e["time_start"] = parsed
                    break
            save_user_data(user_id, data)
            clear_state(user_id)
            schedule_user(user_id, load_user_data(user_id))
            send_message(user_id, f"✅ Время начала изменено на: {parsed}")
            show_edit_menu(user_id, state["event_id"])
        else:
            send_message(user_id, "❌ Не распознано. Попробуйте: 1430 или 14:30")
    
    # Редактирование времени окончания
    elif step == "edit_end":
        parsed = parse_time(text)
        if parsed:
            data = load_user_data(user_id)
            for e in data["events"]:
                if e["id"] == state["event_id"]:
                    e["time_end"] = parsed
                    break
            save_user_data(user_id, data)
            clear_state(user_id)
            schedule_user(user_id, load_user_data(user_id))
            send_message(user_id, f"✅ Время окончания изменено на: {parsed}")
            show_edit_menu(user_id, state["event_id"])
        else:
            send_message(user_id, "❌ Не распознано. Попробуйте: 1530 или 15:30")
    
    clear_state(user_id)

def handle_button(user_id, button_text):
    data = load_user_data(user_id)
    state = get_state(user_id)
    
    # Главное меню
    if button_text == "📅 Распорядок":
        show_schedule(user_id)
    elif button_text == "⚙️ Настройки":
        status = "🟢 ВКЛЮЧЕНЫ" if data["enabled"] else "🔴 ВЫКЛЮЧЕНЫ"
        keyboard = VkKeyboard(one_time=False)
        if data["enabled"]:
            keyboard.add_button("🔴 ВЫКЛЮЧИТЬ ВСЕ", color=VkKeyboardColor.NEGATIVE)
        else:
            keyboard.add_button("🟢 ВКЛЮЧИТЬ ВСЕ", color=VkKeyboardColor.POSITIVE)
        keyboard.add_line()
        keyboard.add_button("◀️ Назад", color=VkKeyboardColor.SECONDARY)
        send_message(user_id, f"⚙️ *НАСТРОЙКИ*\n\nУведомления: {status}", keyboard)
    elif button_text == "🏠 Главное меню":
        send_start(user_id)
    elif button_text == "◀️ Назад":
        send_start(user_id)
    
    # Меню редактирования
    elif button_text == "✏️ Редактировать":
        send_message(user_id, "Выберите действие:", get_edit_keyboard())
    elif button_text == "✏️ Редактировать событие":
        show_events_list(user_id, "edit")
    elif button_text == "🗑️ Удалить событие":
        show_events_list(user_id, "delete")
    elif button_text == "➕ Добавить событие":
        add_event_start(user_id)
    
    # Глобальные настройки
    elif button_text == "🔴 ВЫКЛЮЧИТЬ ВСЕ" or button_text == "🟢 ВКЛЮЧИТЬ ВСЕ":
        data["enabled"] = not data["enabled"]
        save_user_data(user_id, data)
        schedule_user(user_id, data)
        send_message(user_id, f"✅ Уведомления {'ВЫКЛЮЧЕНЫ' if not data['enabled'] else 'ВКЛЮЧЕНЫ'}")
        show_schedule(user_id)
    
    # Выбор события для редактирования/удаления
    elif state.get("step") == "select_edit":
        try:
            event_title = button_text.split(" - ", 1)[1]
            for e in data["events"]:
                if e["title"] == event_title or button_text.startswith(e["time_start"]):
                    show_edit_menu(user_id, e["id"])
                    break
        except:
            pass
        clear_state(user_id)
    
    elif state.get("step") == "select_delete":
        try:
            event_title = button_text.split(" - ", 1)[1]
            for e in data["events"]:
                if e["title"] == event_title or button_text.startswith(e["time_start"]):
                    data["events"] = [ev for ev in data["events"] if ev["id"] != e["id"]]
                    save_user_data(user_id, data)
                    schedule_user(user_id, data)
                    send_message(user_id, f"✅ Событие удалено")
                    show_schedule(user_id)
                    break
        except:
            pass
        clear_state(user_id)
    
    # Редактирование конкретного события
    elif button_text == "📝 Изменить название":
        state["step"] = "edit_title"
        send_message(user_id, "📝 Введите новое название:", get_cancel_keyboard())
    elif button_text == "⏰ Изменить время начала":
        state["step"] = "edit_start"
        send_message(user_id, "⏰ Введите новое время начала (например: 1430 или 14:30):", get_cancel_keyboard())
    elif button_text == "⏰ Изменить время окончания":
        state["step"] = "edit_end"
        send_message(user_id, "⏰ Введите новое время окончания (например: 1530 или 15:30):", get_cancel_keyboard())
    elif button_text == "🔔 Уведомление за (мин)":
        keyboard = VkKeyboard(one_time=False)
        keyboard.add_button("0 мин", color=VkKeyboardColor.PRIMARY)
        keyboard.add_button("5 мин", color=VkKeyboardColor.PRIMARY)
        keyboard.add_button("10 мин", color=VkKeyboardColor.PRIMARY)
        keyboard.add_button("15 мин", color=VkKeyboardColor.PRIMARY)
        keyboard.add_button("30 мин", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        keyboard.add_button("◀️ Назад", color=VkKeyboardColor.SECONDARY)
        send_message(user_id, "🔔 За сколько минут прислать уведомление?", keyboard)
    elif button_text in ["0 мин", "5 мин", "10 мин", "15 мин", "30 мин"]:
        before = int(button_text.split()[0])
        for e in data["events"]:
            if e["id"] == state.get("event_id"):
                e["notification_minutes_before"] = before
                break
        save_user_data(user_id, data)
        schedule_user(user_id, data)
        send_message(user_id, f"✅ Уведомление: {'точно в время' if before == 0 else f'за {before} мин'}")
        show_edit_menu(user_id, state["event_id"])
    elif button_text.startswith("🔔"):
        for e in data["events"]:
            if e["id"] == state.get("event_id"):
                e["notification_enabled"] = not e.get("notification_enabled", True)
                break
        save_user_data(user_id, data)
        schedule_user(user_id, data)
        show_edit_menu(user_id, state["event_id"])
    
    elif button_text == "❌ Отмена":
        clear_state(user_id)
        send_start(user_id)

def main():
    print("✅ Запуск ВК бота...")
    vk_session = VkApi(token=TOKEN)
    vk = vk_session.get_api()
    longpoll = VkBotLongPoll(vk_session, GROUP_ID)
    
    print(f"✅ Бот запущен! Group ID: {GROUP_ID}")
    
    # Запускаем планировщики для всех существующих пользователей
    for filename in os.listdir(DATA_DIR):
        if filename.startswith("user_") and filename.endswith(".json"):
            user_id = int(filename.split("_")[1].split(".")[0])
            data = load_user_data(user_id)
            schedule_user(user_id, data)
    
    for event in longpoll.listen():
        if event.type == VkBotEventType.MESSAGE_NEW:
            try:
                msg = event.object.message
                user_id = msg['from_id']
                text = msg.get('text', '')
                payload = msg.get('payload')
                
                # Инициализация пользователя
                load_user_data(user_id)
                
                if text == "/start":
                    send_start(user_id)
                elif payload:
                    handle_button(user_id, payload)
                elif text:
                    handle_text(user_id, text)
            except Exception as e:
                print(f"Ошибка обработки: {e}")
                import traceback
                traceback.print_exc()

if __name__ == "__main__":
    main()
