import asyncio
import random
import json
import re
import os
from telethon import TelegramClient, errors, functions, types as telethon_types, events
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
# Добавь ЭТО В САМОЕ НАЧАЛО bot.py (после импортов)
import sys
import fcntl
import os

# Блокировка от двойного запуска
lock_file = open("bot.lock", "w")
try:
    fcntl.lockf(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
except IOError:
    print("[ERROR] Бот уже запущен! Закрой другой экземпляр!")
    sys.exit(0)
# ========== КОНФИГИ ==========
API_ID = 21221252
API_HASH = "a9404d19991d37fac90124ec750bcd1d"
BOT_TOKEN = "8580248890:AAFumXO2yAWzaXP9ahkQwFRL-rRFk6OQy0U"
USERS_FILE = "users_data.json"

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
users_data = {}
pending_auth = {}
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)  # В 2.x нужно передавать bot!

def load_users():
    global users_data
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
            for user_id, data in saved.items():
                users_data[int(user_id)] = {
                    **data,
                    "client": None,
                    "task": None,
                    "monitor_task": None
                }
    except:
        users_data = {}

def save_users():
    to_save = {}
    for user_id, data in users_data.items():
        to_save[str(user_id)] = {
            "phone": data.get("phone"),
            "running": data.get("running", False),
            "targets": data.get("targets", []),
            "message_groups": data.get("message_groups", []),
            "delay_min": data.get("delay_min", 5),
            "delay_max": data.get("delay_max", 10)
        }
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=2, ensure_ascii=False)

def create_new_user(user_id: int):
    users_data[user_id] = {
        "phone": None,
        "client": None,
        "running": False,
        "targets": [],
        "message_groups": [],
        "delay_min": 5,
        "delay_max": 10,
        "task": None,
        "monitor_task": None
    }
    save_users()

def decode_code(encoded_string: str) -> str:
    if not encoded_string:
        return ""
    encoded_string = re.sub(r'(?i)code[\s:]+', '', encoded_string.strip())
    digits = re.sub(r'\D', '', encoded_string)
    return digits if len(digits) >= 4 else ""

# ========== АВТОМАТИЧЕСКОЕ РЕШЕНИЕ ==========
async def auto_subscribe_to_channel(client, channel_identifier):
    try:
        if 't.me/' in channel_identifier:
            username = channel_identifier.split('t.me/')[-1].split('?')[0].split('/')[0]
        else:
            username = channel_identifier.replace('@', '').strip()
        if not username:
            return False, None
        try:
            entity = await client.get_entity(f"@{username}")
        except:
            entity = await client.get_entity(username)
        await client(functions.channels.JoinChannelRequest(
            telethon_types.InputChannel(entity.id, entity.access_hash)
        ))
        return True, username
    except:
        return False, None

async def auto_solve_captcha(client, message):
    text = message.text.lower() if message.text else ""
    numbers = re.findall(r'\b\d{4,6}\b', text)
    if numbers:
        code = numbers[0]
        await client.send_message(message.chat_id, code)
        return True, f"Цифровая капча: {code}"
    if message.reply_markup:
        for row in message.reply_markup.inline_keyboard:
            for button in row:
                button_text = button.text.lower()
                if any(word in button_text for word in ['не робот', 'captcha', 'verify', 'проверк', 'solve', 'confirm']):
                    await message.click(button.text)
                    return True, f"Кнопка: {button.text}"
    return False, None

async def auto_monitor_messages(client, user_id):
    print(f"[MONITOR:{user_id}] Автомониторинг запущен")
    @client.on(events.NewMessage)
    async def handler(event):
        if event.chat_id != user_id:
            return
        message = event.message
        text = message.text.lower() if message.text else ""
        channel_patterns = [r'(?:https?://)?(?:www\.)?t\.me/([a-zA-Z0-9_]+)', r'@([a-zA-Z0-9_]+)']
        channels_found = []
        for pattern in channel_patterns:
            matches = re.findall(pattern, text)
            channels_found.extend(matches)
        for channel in set(channels_found):
            if len(channel) > 3:
                await auto_subscribe_to_channel(client, channel)
        await auto_solve_captcha(client, message)
        if 'подпишись' in text or 'подписаться' in text:
            all_links = re.findall(r'(?:https?://)?(?:www\.)?[a-zA-Z0-9_\-\.]+', text)
            for link in all_links:
                if 't.me' in link or link.startswith('@'):
                    await auto_subscribe_to_channel(client, link)

async def send_loop_for_user(user_id: int):
    print(f"[USERBOT:{user_id}] Запущен")
    while True:
        if user_id not in users_data:
            break
        user = users_data[user_id]
        if not user.get("running"):
            await asyncio.sleep(2)
            continue
        message_groups = user.get("message_groups", [])
        targets = user.get("targets", [])
        delay_min = user.get("delay_min", 5)
        delay_max = user.get("delay_max", 10)
        if not message_groups or not targets:
            await asyncio.sleep(3)
            continue
        client = user.get("client")
        if not client:
            await asyncio.sleep(5)
            continue
        for target in targets:
            for group in message_groups:
                if user_id not in users_data or not users_data[user_id].get("running"):
                    break
                for msg in group:
                    if user_id not in users_data or not users_data[user_id].get("running"):
                        break
                    delay = random.uniform(delay_min, delay_max)
                    await asyncio.sleep(delay)
                    try:
                        await client.send_message(target, msg)
                        print(f"[SENT:{user_id}] -> {target}")
                    except Exception as e:
                        print(f"[ERROR:{user_id}] {e}")
        await asyncio.sleep(3)

async def start_auto_monitoring(client, user_id):
    if user_id in users_data:
        if users_data[user_id].get("monitor_task"):
            users_data[user_id]["monitor_task"].cancel()
        monitor_task = asyncio.create_task(auto_monitor_messages(client, user_id))
        users_data[user_id]["monitor_task"] = monitor_task
        return True
    return False

# ========== КНОПКИ МЕНЮ ==========
def get_main_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📊 Статус", callback_data="status"),
        InlineKeyboardButton("▶️ Старт", callback_data="start_spam"),
        InlineKeyboardButton("⏹️ Стоп", callback_data="stop_spam")
    )
    keyboard.add(
        InlineKeyboardButton("🎯 Цели", callback_data="targets_menu"),
        InlineKeyboardButton("💬 Сообщения", callback_data="messages_menu")
    )
    keyboard.add(
        InlineKeyboardButton("⚙️ Задержка", callback_data="delay_menu"),
        InlineKeyboardButton("🔐 Аккаунт", callback_data="account_menu")
    )
    return keyboard

def get_targets_keyboard(user_id):
    targets = users_data.get(user_id, {}).get("targets", [])
    keyboard = InlineKeyboardMarkup(row_width=1)
    for i, target in enumerate(targets):
        keyboard.add(InlineKeyboardButton(f"❌ {target}", callback_data=f"del_target_{i}"))
    keyboard.add(InlineKeyboardButton("➕ Добавить цель", callback_data="add_target"))
    keyboard.add(InlineKeyboardButton("🗑️ Очистить все", callback_data="clear_targets"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_main"))
    return keyboard

def get_messages_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("➕ Добавить группу", callback_data="add_group"))
    keyboard.add(InlineKeyboardButton("📋 Список групп", callback_data="list_groups"))
    keyboard.add(InlineKeyboardButton("🗑️ Очистить все", callback_data="clear_groups"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_main"))
    return keyboard

def get_delay_keyboard(current_min, current_max):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🐢 3-7 сек", callback_data="delay_3_7"),
        InlineKeyboardButton("⚡ 5-10 сек", callback_data="delay_5_10"),
        InlineKeyboardButton("🐌 10-20 сек", callback_data="delay_10_20"),
        InlineKeyboardButton("🎲 15-30 сек", callback_data="delay_15_30")
    )
    keyboard.add(InlineKeyboardButton(f"📊 Текущие: {current_min}-{current_max} сек", callback_data="noop"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_main"))
    return keyboard

def get_account_keyboard(is_logged):
    keyboard = InlineKeyboardMarkup(row_width=1)
    if not is_logged:
        keyboard.add(InlineKeyboardButton("📱 Войти", callback_data="login_start"))
    else:
        keyboard.add(InlineKeyboardButton("👤 Инфо", callback_data="account_info"))
        keyboard.add(InlineKeyboardButton("🚪 Выйти", callback_data="logout"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_main"))
    return keyboard

# ========== ОБРАБОТЧИКИ ==========
@dp.message_handler(commands=['start'])
async def cmd_start(message: Message):
    user_id = message.from_user.id
    if user_id not in users_data:
        create_new_user(user_id)
        await message.answer(
            "✨ **Добро пожаловать!** ✨\n\n"
            "🤖 Бот сам решает капчи и подписывается на спонсоров\n\n"
            "🔐 Сначала войди в аккаунт: нажми 'Аккаунт' → 'Войти'",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer("✨ Главное меню ✨", reply_markup=get_main_keyboard())

@dp.callback_query_handler(lambda c: True)
async def handle_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data
    
    if user_id not in users_data:
        create_new_user(user_id)
    
    user = users_data[user_id]
    is_logged = user.get("client") is not None
    
    if data == "status":
        await callback.message.edit_text(
            f"📊 **СТАТУС**\n\n"
            f"🔐 Аккаунт: {'✅ ВОШЕЛ' if is_logged else '❌ НЕ ВОШЕЛ'}\n"
            f"📱 Номер: {user.get('phone', '❌')}\n"
            f"▶️ Рассылка: {'🟢 АКТИВНА' if user.get('running') else '🔴 ОСТАНОВЛЕНА'}\n"
            f"🎯 Целей: {len(user.get('targets', []))}\n"
            f"💬 Групп: {len(user.get('message_groups', []))}\n"
            f"⏱️ Задержка: {user.get('delay_min', 5)}-{user.get('delay_max', 10)} сек\n\n"
            f"🛡️ АВТО-ЗАЩИТА АКТИВНА",
            reply_markup=get_main_keyboard()
        )
    
    elif data == "start_spam":
        if not is_logged:
            await callback.answer("❌ Сначала войди в аккаунт!", show_alert=True)
        else:
            user["running"] = True
            save_users()
            if user.get("client") and not user.get("task"):
                user["task"] = asyncio.create_task(send_loop_for_user(user_id))
            await callback.answer("✅ Рассылка запущена!", show_alert=True)
            await callback.message.edit_text("✅ Рассылка запущена!", reply_markup=get_main_keyboard())
    
    elif data == "stop_spam":
        user["running"] = False
        save_users()
        await callback.answer("⏹️ Рассылка остановлена!", show_alert=True)
        await callback.message.edit_text("⏹️ Рассылка остановлена", reply_markup=get_main_keyboard())
    
    elif data == "targets_menu":
        targets = user.get("targets", [])
        if not targets:
            await callback.message.edit_text("🎯 Список целей пуст", reply_markup=get_targets_keyboard(user_id))
        else:
            targets_list = "\n".join([f"• {t}" for t in targets])
            await callback.message.edit_text(f"🎯 Цели:\n{targets_list}", reply_markup=get_targets_keyboard(user_id))
    
    elif data == "add_target":
        await callback.message.edit_text("➕ Отправь команду: /addtarget @username", reply_markup=get_targets_keyboard(user_id))
    
    elif data.startswith("del_target_"):
        idx = int(data.split("_")[2])
        targets = user.get("targets", [])
        if 0 <= idx < len(targets):
            removed = targets.pop(idx)
            user["targets"] = targets
            save_users()
            await callback.answer(f"✅ Удалено: {removed}", show_alert=True)
            targets_list = "\n".join([f"• {t}" for t in targets]) if targets else "🎯 Список целей пуст"
            await callback.message.edit_text(f"🎯 Цели:\n{targets_list}", reply_markup=get_targets_keyboard(user_id))
    
    elif data == "clear_targets":
        user["targets"] = []
        save_users()
        await callback.answer("🗑️ Все цели очищены!", show_alert=True)
        await callback.message.edit_text("🎯 Цели очищены", reply_markup=get_targets_keyboard(user_id))
    
    elif data == "messages_menu":
        groups = user.get("message_groups", [])
        total_msgs = sum(len(g) for g in groups)
        await callback.message.edit_text(f"💬 Групп: {len(groups)}\n📝 Сообщений: {total_msgs}", reply_markup=get_messages_keyboard())
    
    elif data == "list_groups":
        groups = user.get("message_groups", [])
        if not groups:
            await callback.message.edit_text("📋 Нет групп", reply_markup=get_messages_keyboard())
        else:
            text = "📋 Твои группы:\n\n"
            for i, group in enumerate(groups, 1):
                text += f"Группа {i} ({len(group)} сообщений):\n"
                for j, msg in enumerate(group[:2], 1):
                    preview = msg[:40] + "..." if len(msg) > 40 else msg
                    text += f"  {j}. {preview}\n"
                if len(group) > 2:
                    text += f"  ... и еще {len(group)-2}\n"
                text += "\n"
            await callback.message.edit_text(text, reply_markup=get_messages_keyboard())
    
    elif data == "add_group":
        await callback.message.edit_text("➕ Отправь команду: /addgroup текст1 | текст2 | текст3", reply_markup=get_messages_keyboard())
    
    elif data == "clear_groups":
        user["message_groups"] = []
        save_users()
        await callback.answer("🗑️ Все группы очищены!", show_alert=True)
        await callback.message.edit_text("💬 Группы очищены", reply_markup=get_messages_keyboard())
    
    elif data == "delay_menu":
        await callback.message.edit_text(f"⚙️ Текущая задержка: {user.get('delay_min', 5)}-{user.get('delay_max', 10)} сек", reply_markup=get_delay_keyboard(user.get('delay_min', 5), user.get('delay_max', 10)))
    
    elif data.startswith("delay_"):
        if data == "delay_3_7":
            user["delay_min"], user["delay_max"] = 3, 7
        elif data == "delay_5_10":
            user["delay_min"], user["delay_max"] = 5, 10
        elif data == "delay_10_20":
            user["delay_min"], user["delay_max"] = 10, 20
        elif data == "delay_15_30":
            user["delay_min"], user["delay_max"] = 15, 30
        else:
            await callback.answer()
            return
        save_users()
        await callback.answer(f"✅ Задержка: {user['delay_min']}-{user['delay_max']} сек", show_alert=True)
        await callback.message.edit_text(f"⚙️ Задержка обновлена: {user['delay_min']}-{user['delay_max']} сек", reply_markup=get_delay_keyboard(user['delay_min'], user['delay_max']))
    
    elif data == "account_menu":
        await callback.message.edit_text(f"🔐 Аккаунт\nСтатус: {'✅ ВОШЕЛ' if is_logged else '❌ НЕ ВОШЕЛ'}\n📱 Номер: {user.get('phone', '❌')}", reply_markup=get_account_keyboard(is_logged))
    
    elif data == "login_start":
        await callback.message.edit_text("📱 Вход\n1. /login +71234567890\n2. /code 1#2#3#4#5\n3. /password пароль", reply_markup=get_account_keyboard(is_logged))
    
    elif data == "account_info":
        if is_logged and user.get("client"):
            try:
                me = await user["client"].get_me()
                await callback.answer(f"👤 {me.first_name}", show_alert=True)
            except:
                await callback.answer("❌ Ошибка", show_alert=True)
        else:
            await callback.answer("❌ Не авторизован", show_alert=True)
    
    elif data == "logout":
        if user.get("client"):
            await user["client"].disconnect()
        if user.get("task"):
            user["task"].cancel()
        if user.get("monitor_task"):
            user["monitor_task"].cancel()
        user["client"] = None
        user["task"] = None
        user["monitor_task"] = None
        user["running"] = False
        user["phone"] = None
        save_users()
        await callback.answer("🚪 Вышел!", show_alert=True)
        await callback.message.edit_text("🔐 Вы вышли из аккаунта", reply_markup=get_account_keyboard(False))
    
    elif data == "back_main":
        await callback.message.edit_text("✨ Главное меню ✨", reply_markup=get_main_keyboard())
    
    await callback.answer()

# ========== КОМАНДЫ ==========
@dp.message_handler(commands=['login'])
async def cmd_login(message: Message):
    user_id = message.from_user.id
    phone = message.text.replace("/login", "").strip()
    if not phone or not phone.startswith("+"):
        await message.answer("❌ /login +71234567890")
        return
    if user_id in users_data and users_data[user_id].get("client"):
        await message.answer("❌ Ты уже авторизован! Используй /logout")
        return
    try:
        session_name = f"user_{user_id}_{phone.replace('+', '')}"
        client = TelegramClient(session_name, API_ID, API_HASH)
        await client.connect()
        await client.send_code_request(phone)
        pending_auth[user_id] = {"step": "waiting_code", "client": client, "phone": phone, "session_name": session_name}
        await message.answer(f"📱 Код отправлен на {phone}\nОтправь: /code 1#2#3#4#5")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@dp.message_handler(commands=['code'])
async def cmd_code(message: Message):
    user_id = message.from_user.id
    raw_code = message.text.replace("/code", "").strip()
    if user_id not in pending_auth:
        await message.answer("❌ Сначала /login")
        return
    auth_data = pending_auth[user_id]
    code = decode_code(raw_code)
    if not code or len(code) < 4:
        await message.answer("❌ Не могу распознать код")
        return
    await message.answer(f"🔍 Распознал код: {code}")
    try:
        client = auth_data["client"]
        phone = auth_data["phone"]
        await client.sign_in(phone, code=code)
        if user_id not in users_data:
            create_new_user(user_id)
        users_data[user_id]["client"] = client
        users_data[user_id]["phone"] = phone
        await start_auto_monitoring(client, user_id)
        save_users()
        del pending_auth[user_id]
        await message.answer(f"✅ Успешный вход!\n🛡️ Авто-защита запущена!", reply_markup=get_main_keyboard())
    except errors.SessionPasswordNeededError:
        pending_auth[user_id]["step"] = "need_password"
        await message.answer("🔐 Нужен 2FA пароль! /password ПАРОЛЬ")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@dp.message_handler(commands=['password'])
async def cmd_password(message: Message):
    user_id = message.from_user.id
    password = message.text.replace("/password", "").strip()
    if user_id not in pending_auth:
        await message.answer("❌ Сначала /login")
        return
    auth_data = pending_auth[user_id]
    try:
        client = auth_data["client"]
        phone = auth_data["phone"]
        await client.sign_in(password=password)
        if user_id not in users_data:
            create_new_user(user_id)
        users_data[user_id]["client"] = client
        users_data[user_id]["phone"] = phone
        await start_auto_monitoring(client, user_id)
        save_users()
        del pending_auth[user_id]
        await message.answer(f"✅ Успешный вход с 2FA!", reply_markup=get_main_keyboard())
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@dp.message_handler(commands=['addtarget'])
async def cmd_add_target(message: Message):
    user_id = message.from_user.id
    target = message.text.replace("/addtarget", "").strip()
    if not target:
        await message.answer("❌ /addtarget @username")
        return
    if user_id not in users_data:
        create_new_user(user_id)
    if target not in users_data[user_id]["targets"]:
        users_data[user_id]["targets"].append(target)
        save_users()
        await message.answer(f"✅ Цель добавлена: {target}")
    else:
        await message.answer(f"⚠️ Цель уже есть")

@dp.message_handler(commands=['addgroup'])
async def cmd_add_group(message: Message):
    user_id = message.from_user.id
    text = message.text.replace("/addgroup", "").strip()
    if not text:
        await message.answer("❌ /addgroup текст1 | текст2 | текст3")
        return
    group = [x.strip() for x in text.split("|") if x.strip()]
    if not group:
        await message.answer("❌ Пустая группа")
        return
    if user_id not in users_data:
        create_new_user(user_id)
    users_data[user_id]["message_groups"].append(group)
    save_users()
    await message.answer(f"✅ Группа добавлена! {len(group)} сообщений")

@dp.message_handler(commands=['logout'])
async def cmd_logout(message: Message):
    user_id = message.from_user.id
    if user_id in users_data:
        if users_data[user_id].get("client"):
            await users_data[user_id]["client"].disconnect()
        if users_data[user_id].get("task"):
            users_data[user_id]["task"].cancel()
        if users_data[user_id].get("monitor_task"):
            users_data[user_id]["monitor_task"].cancel()
        users_data[user_id] = {
            "phone": None, "client": None, "running": False, "targets": [],
            "message_groups": [], "delay_min": 5, "delay_max": 10,
            "task": None, "monitor_task": None
        }
        save_users()
        await message.answer("🚪 Вышел из аккаунта")
    else:
        await message.answer("❌ Не авторизован")

# ========== ЗАПУСК ==========
async def main():
    load_users()
    print("=" * 50)
    print("🤖 БОТ ЗАПУЩЕН НА RAILWAY")
    print("🛡️ АВТО-ЗАЩИТА АКТИВНА")
    print("=" * 50)
    for user_id, user in users_data.items():
        if user.get("client"):
            await start_auto_monitoring(user["client"], user_id)
            if user.get("running"):
                user["task"] = asyncio.create_task(send_loop_for_user(user_id))
    await dp.start_polling()

if __name__ == "__main__":
    asyncio.run(main())
