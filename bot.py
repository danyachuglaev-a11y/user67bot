import asyncio
import random
import json
import re
import os
from telethon import TelegramClient, errors, events
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from aiogram.filters import Command

# ========== КОНФИГИ ==========
API_ID = 26259835
API_HASH = "3fa32264398920f001dd2428b42060f6"
BOT_TOKEN = "8634998743:AAFSu5he1x_mLaJ6wKHtSDWKVC7qb9zhUnM"
USERS_FILE = "users_data.json"

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
users_data = {}
pending_auth = {}
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ========== ЗАГРУЗКА/СОХРАНЕНИЕ ==========
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
            "delay_max": data.get("delay_max", 10),
            "temp_photos": data.get("temp_photos", [])
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
        "monitor_task": None,
        "temp_photos": []  # Хранилище для фото
    }
    save_users()

def decode_code(encoded_string: str) -> str:
    if not encoded_string:
        return ""
    encoded_string = re.sub(r'(?i)code[\s:]+', '', encoded_string.strip())
    digits = re.sub(r'\D', '', encoded_string)
    return digits if len(digits) >= 4 else ""

# ========== ФУНКЦИЯ ДЛЯ ОТПРАВКИ (ТЕКСТ + ФОТО) ==========
async def send_item(client, target, item):
    """Отправляет текст или фото"""
    if isinstance(item, dict) and item.get("type") == "photo":
        # Отправляем фото
        try:
            file_path = item.get("file_path")
            caption = item.get("caption", "")
            if file_path and os.path.exists(file_path):
                await client.send_file(target, file_path, caption=caption)
            else:
                # Если файл не найден, пробуем по file_id
                await client.send_file(target, item.get("file_id"), caption=caption)
            return True
        except Exception as e:
            print(f"Ошибка отправки фото: {e}")
            return False
    else:
        # Отправляем текст
        await client.send_message(target, str(item))
        return True

# ========== СОХРАНЕНИЕ ФОТО ==========
async def save_photo(user_id, message: Message):
    """Сохраняет фото из сообщения"""
    if not message.photo:
        return False, None
    
    # Создаем папку для фото если нет
    if not os.path.exists("photos"):
        os.makedirs("photos")
    
    # Получаем фото
    photo = message.photo[-1]
    file_id = photo.file_id
    
    # Сохраняем информацию о фото
    photo_info = {
        "type": "photo",
        "file_id": file_id,
        "caption": message.caption or "",
        "file_path": None
    }
    
    # Пытаемся скачать файл
    try:
        file = await bot.get_file(file_id)
        file_path = f"photos/user_{user_id}_{int(asyncio.get_event_loop().time())}.jpg"
        await bot.download_file(file.file_path, file_path)
        photo_info["file_path"] = file_path
    except:
        pass
    
    return True, photo_info

# ========== ЮЗЕРБОТ ==========
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
                for item in group:
                    if user_id not in users_data or not users_data[user_id].get("running"):
                        break
                    delay = random.uniform(delay_min, delay_max)
                    await asyncio.sleep(delay)
                    try:
                        await send_item(client, target, item)
                        print(f"[SENT:{user_id}] -> {target}")
                    except Exception as e:
                        print(f"[ERROR:{user_id}] {e}")
        await asyncio.sleep(3)

# ========== МОНИТОРИНГ ==========
async def auto_monitor_messages(client, user_id):
    print(f"[MONITOR:{user_id}] Мониторинг запущен")
    
    @client.on(events.NewMessage)
    async def handler(event):
        if event.chat_id != user_id:
            return
        # Тут можно добавить авто-решение капч
        pass

async def start_auto_monitoring(client, user_id):
    if user_id in users_data:
        if users_data[user_id].get("monitor_task"):
            users_data[user_id]["monitor_task"].cancel()
        monitor_task = asyncio.create_task(auto_monitor_messages(client, user_id))
        users_data[user_id]["monitor_task"] = monitor_task
        return True
    return False

# ========== КНОПКИ МЕНЮ (ТЕ ЖЕ САМЫЕ) ==========
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
    keyboard.add(InlineKeyboardButton("📝 Добавить текст", callback_data="add_text"))
    keyboard.add(InlineKeyboardButton("📸 Добавить фото", callback_data="add_photo"))
    keyboard.add(InlineKeyboardButton("📋 Список сообщений", callback_data="list_messages"))
    keyboard.add(InlineKeyboardButton("🗑️ Очистить всё", callback_data="clear_messages"))
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
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    if user_id not in users_data:
        create_new_user(user_id)
        await message.answer(
            "✨ **Добро пожаловать!** ✨\n\n"
            "🤖 Твой бот для рассылки\n\n"
            "🔐 **Сначала войди:**\n"
            "Аккаунт → Войти\n\n"
            "👇 Используй кнопки 👇",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            "✨ **Главное меню** ✨",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )

@dp.callback_query()
async def handle_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data
    
    if user_id not in users_data:
        create_new_user(user_id)
    
    user = users_data[user_id]
    is_logged = user.get("client") is not None
    
    # СТАТУС
    if data == "status":
        await callback.message.edit_text(
            f"📊 **СТАТУС**\n\n"
            f"🔐 Аккаунт: {'✅ ВОШЕЛ' if is_logged else '❌ НЕ ВОШЕЛ'}\n"
            f"📱 Номер: {user.get('phone', '❌')}\n"
            f"▶️ Рассылка: {'🟢 АКТИВНА' if user.get('running') else '🔴 ОСТАНОВЛЕНА'}\n"
            f"🎯 Целей: {len(user.get('targets', []))}\n"
            f"💬 Сообщений: {len(user.get('message_groups', []))}\n"
            f"⏱️ Задержка: {user.get('delay_min', 5)}-{user.get('delay_max', 10)} сек",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    
    # ЗАПУСК
    elif data == "start_spam":
        if not is_logged:
            await callback.answer("❌ Сначала войди в аккаунт!", show_alert=True)
        else:
            user["running"] = True
            save_users()
            if user.get("client") and not user.get("task"):
                user["task"] = asyncio.create_task(send_loop_for_user(user_id))
            await callback.answer("✅ Рассылка запущена!", show_alert=True)
            await callback.message.edit_text(
                "✅ **Рассылка запущена!**",
                reply_markup=get_main_keyboard(),
                parse_mode="Markdown"
            )
    
    # ОСТАНОВКА
    elif data == "stop_spam":
        user["running"] = False
        save_users()
        await callback.answer("⏹️ Рассылка остановлена!", show_alert=True)
        await callback.message.edit_text(
            "⏹️ **Рассылка остановлена**",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    
    # ЦЕЛИ - МЕНЮ
    elif data == "targets_menu":
        targets = user.get("targets", [])
        if not targets:
            await callback.message.edit_text(
                "🎯 **Управление целями**\n\nСписок целей пуст.\n\n➕ Добавь цель: `/addtarget @username`",
                reply_markup=get_targets_keyboard(user_id),
                parse_mode="Markdown"
            )
        else:
            targets_list = "\n".join([f"• {t}" for t in targets])
            await callback.message.edit_text(
                f"🎯 **Цели ({len(targets)}):**\n\n{targets_list}",
                reply_markup=get_targets_keyboard(user_id),
                parse_mode="Markdown"
            )
    
    # ДОБАВИТЬ ЦЕЛЬ
    elif data == "add_target":
        await callback.message.edit_text(
            "➕ **Добавление цели**\n\n"
            "Отправь команду:\n`/addtarget @username`\n\n"
            "Пример: `/addtarget @durov`",
            reply_markup=get_targets_keyboard(user_id),
            parse_mode="Markdown"
        )
    
    # УДАЛИТЬ ЦЕЛЬ
    elif data.startswith("del_target_"):
        idx = int(data.split("_")[2])
        targets = user.get("targets", [])
        if 0 <= idx < len(targets):
            removed = targets.pop(idx)
            user["targets"] = targets
            save_users()
            await callback.answer(f"✅ Удалено: {removed}", show_alert=True)
            await callback.message.edit_text(
                f"🎯 **Цели ({len(targets)}):**\n\n" + "\n".join([f"• {t}" for t in targets]) if targets else "🎯 Список целей пуст",
                reply_markup=get_targets_keyboard(user_id),
                parse_mode="Markdown"
            )
    
    # ОЧИСТИТЬ ЦЕЛИ
    elif data == "clear_targets":
        user["targets"] = []
        save_users()
        await callback.answer("🗑️ Все цели очищены!", show_alert=True)
        await callback.message.edit_text(
            "🎯 **Цели очищены**",
            reply_markup=get_targets_keyboard(user_id),
            parse_mode="Markdown"
        )
    
    # СООБЩЕНИЯ - МЕНЮ
    elif data == "messages_menu":
        groups = user.get("message_groups", [])
        total = len(groups)
        await callback.message.edit_text(
            f"💬 **Управление сообщениями**\n\n"
            f"📊 Сообщений в очереди: {total}\n\n"
            f"📝 **Текст:** просто отправь команду /addgroup\n"
            f"📸 **Фото:** нажми 'Добавить фото' и перешли фото\n\n"
            f"💡 Сообщения отправляются в том порядке, в котором ты их добавил",
            reply_markup=get_messages_keyboard(),
            parse_mode="Markdown"
        )
    
    # ДОБАВИТЬ ТЕКСТ
    elif data == "add_text":
        await callback.message.edit_text(
            "📝 **Добавление текста**\n\n"
            "Отправь команду:\n`/addgroup твой текст`\n\n"
            "Пример: `/addgroup Привет! Как дела?`\n\n"
            "💡 Если нужно несколько сообщений - используй |\n"
            "`/addgroup Привет! | Как дела? | Пока!`",
            reply_markup=get_messages_keyboard(),
            parse_mode="Markdown"
        )
    
    # ДОБАВИТЬ ФОТО
    elif data == "add_photo":
        user["waiting_for_photo"] = True
        save_users()
        await callback.message.edit_text(
            "📸 **Добавление фото**\n\n"
            "1️⃣ **Просто отправь фото** (можно с подписью)\n"
            "2️⃣ Бот автоматически сохранит его\n"
            "3️⃣ Фото добавится в очередь сообщений\n\n"
            "💡 Можно отправить несколько фото подряд\n"
            "💡 Подпись к фото тоже отправится\n\n"
            "📤 **Отправь фото прямо сейчас!**",
            reply_markup=get_messages_keyboard(),
            parse_mode="Markdown"
        )
    
    # СПИСОК СООБЩЕНИЙ
    elif data == "list_messages":
        groups = user.get("message_groups", [])
        if not groups:
            await callback.message.edit_text(
                "📋 **Список сообщений пуст**\n\nДобавь текст или фото через меню",
                reply_markup=get_messages_keyboard(),
                parse_mode="Markdown"
            )
        else:
            text = "📋 **Твои сообщения:**\n\n"
            for i, item in enumerate(groups, 1):
                if isinstance(item, dict) and item.get("type") == "photo":
                    caption = item.get("caption", "без подписи")
                    text += f"{i}. 📸 Фото (подпись: {caption[:30]}...)\n"
                else:
                    preview = str(item)[:40] + "..." if len(str(item)) > 40 else str(item)
                    text += f"{i}. 📝 {preview}\n"
            text += f"\n🗑️ Для очистки: кнопка 'Очистить всё'"
            await callback.message.edit_text(
                text,
                reply_markup=get_messages_keyboard(),
                parse_mode="Markdown"
            )
    
    # ОЧИСТИТЬ ВСЕ СООБЩЕНИЯ
    elif data == "clear_messages":
        user["message_groups"] = []
        save_users()
        await callback.answer("🗑️ Все сообщения очищены!", show_alert=True)
        await callback.message.edit_text(
            "💬 **Сообщения очищены**",
            reply_markup=get_messages_keyboard(),
            parse_mode="Markdown"
        )
    
    # ЗАДЕРЖКА - МЕНЮ
    elif data == "delay_menu":
        await callback.message.edit_text(
            f"⚙️ **Настройка задержки**\n\n"
            f"📊 Текущая: {user.get('delay_min', 5)}-{user.get('delay_max', 10)} сек\n\n"
            f"⚠️ Маленькая задержка = риск бана",
            reply_markup=get_delay_keyboard(user.get('delay_min', 5), user.get('delay_max', 10)),
            parse_mode="Markdown"
        )
    
    # УСТАНОВИТЬ ЗАДЕРЖКУ
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
        await callback.message.edit_text(
            f"⚙️ **Задержка обновлена!**\n\n✅ {user['delay_min']}-{user['delay_max']} секунд",
            reply_markup=get_delay_keyboard(user['delay_min'], user['delay_max']),
            parse_mode="Markdown"
        )
    
    # АККАУНТ - МЕНЮ
    elif data == "account_menu":
        await callback.message.edit_text(
            f"🔐 **Аккаунт**\n\n"
            f"📊 Статус: {'✅ ВОШЕЛ' if is_logged else '❌ НЕ ВОШЕЛ'}\n"
            f"📱 Номер: {user.get('phone', '❌')}",
            reply_markup=get_account_keyboard(is_logged),
            parse_mode="Markdown"
        )
    
    # НАЧАЛО ЛОГИНА
    elif data == "login_start":
        await callback.message.edit_text(
            "📱 **Вход в аккаунт**\n\n"
            "**Шаг 1:** Отправь номер\n`/login +71234567890`\n\n"
            "**Шаг 2:** Отправь код\n`/code 1#2#3#4#5`\n\n"
            "**Шаг 3:** Если есть 2FA\n`/password пароль`",
            reply_markup=get_account_keyboard(is_logged),
            parse_mode="Markdown"
        )
    
    # ИНФО АККАУНТА
    elif data == "account_info":
        if is_logged and user.get("client"):
            try:
                me = await user["client"].get_me()
                await callback.answer(f"👤 {me.first_name} (@{me.username})", show_alert=True)
            except:
                await callback.answer("❌ Ошибка", show_alert=True)
        else:
            await callback.answer("❌ Не авторизован", show_alert=True)
    
    # ВЫХОД
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
        await callback.message.edit_text(
            "🔐 **Вы вышли из аккаунта**",
            reply_markup=get_account_keyboard(False),
            parse_mode="Markdown"
        )
    
    # НАЗАД
    elif data == "back_main":
        await callback.message.edit_text(
            "✨ **Главное меню** ✨",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    
    elif data == "noop":
        await callback.answer()
    
    await callback.answer()

# ========== ОБРАБОТКА ФОТО ==========
@dp.message(Command("addgroup"))
async def cmd_add_group(message: Message):
    user_id = message.from_user.id
    text = message.text.replace("/addgroup", "").strip()
    
    if not text:
        await message.answer("❌ Формат: `/addgroup твой текст` или `/addgroup текст1 | текст2`", parse_mode="Markdown")
        return
    
    # Разбиваем на несколько сообщений если есть |
    if "|" in text:
        messages = [x.strip() for x in text.split("|") if x.strip()]
    else:
        messages = [text]
    
    if user_id not in users_data:
        create_new_user(user_id)
    
    # Добавляем каждое сообщение
    for msg in messages:
        users_data[user_id]["message_groups"].append(msg)
    
    save_users()
    await message.answer(
        f"✅ **Добавлено {len(messages)} сообщений!**\n\n"
        f"📊 Всего в очереди: {len(users_data[user_id]['message_groups'])}",
        parse_mode="Markdown"
    )

@dp.message(Command("addphoto"))
async def cmd_add_photo_start(message: Message):
    user_id = message.from_user.id
    
    if user_id not in users_data:
        create_new_user(user_id)
    
    # Включаем режим ожидания фото
    users_data[user_id]["waiting_for_photo"] = True
    save_users()
    
    await message.answer(
        "📸 **Режим добавления фото**\n\n"
        "**Просто отправь фото** (можно с подписью)\n\n"
        "✅ Фото автоматически добавится в очередь\n"
        "💡 Можно отправить несколько фото подряд\n"
        "💡 Чтобы выйти из режима - /cancel",
        parse_mode="Markdown"
    )

@dp.message(Command("cancel"))
async def cmd_cancel(message: Message):
    user_id = message.from_user.id
    
    if user_id in users_data:
        users_data[user_id]["waiting_for_photo"] = False
        save_users()
    
    await message.answer(
        "❌ **Режим добавления фото отключен**",
        parse_mode="Markdown"
    )

@dp.message(Command("addtarget"))
async def cmd_add_target(message: Message):
    user_id = message.from_user.id
    target = message.text.replace("/addtarget", "").strip()
    
    if not target:
        await message.answer("❌ Формат: `/addtarget @username`", parse_mode="Markdown")
        return
    
    if user_id not in users_data:
        create_new_user(user_id)
    
    if target not in users_data[user_id]["targets"]:
        users_data[user_id]["targets"].append(target)
        save_users()
        await message.answer(f"✅ **Цель добавлена:** {target}", parse_mode="Markdown")
    else:
        await message.answer(f"⚠️ Цель уже есть", parse_mode="Markdown")

@dp.message(Command("setdelay"))
async def cmd_set_delay(message: Message):
    user_id = message.from_user.id
    parts = message.text.replace("/setdelay", "").strip().split()
    
    if len(parts) != 2:
        await message.answer("❌ Формат: `/setdelay 5 10`", parse_mode="Markdown")
        return
    
    try:
        delay_min = int(parts[0])
        delay_max = int(parts[1])
        if delay_min < 1 or delay_max < delay_min:
            await message.answer("❌ Неверные значения", parse_mode="Markdown")
            return
        
        if user_id not in users_data:
            create_new_user(user_id)
        
        users_data[user_id]["delay_min"] = delay_min
        users_data[user_id]["delay_max"] = delay_max
        save_users()
        await message.answer(f"✅ **Задержка:** {delay_min}-{delay_max} сек", parse_mode="Markdown")
    except:
        await message.answer("❌ Введи числа", parse_mode="Markdown")

@dp.message(Command("clearmessages"))
async def cmd_clear_messages(message: Message):
    user_id = message.from_user.id
    
    if user_id in users_data:
        count = len(users_data[user_id]["message_groups"])
        users_data[user_id]["message_groups"] = []
        save_users()
        await message.answer(f"🗑️ **Очищено {count} сообщений**", parse_mode="Markdown")
    else:
        await message.answer("❌ Нет данных", parse_mode="Markdown")

@dp.message(Command("cleartargets"))
async def cmd_clear_targets(message: Message):
    user_id = message.from_user.id
    
    if user_id in users_data:
        count = len(users_data[user_id]["targets"])
        users_data[user_id]["targets"] = []
        save_users()
        await message.answer(f"🗑️ **Очищено {count} целей**", parse_mode="Markdown")
    else:
        await message.answer("❌ Нет данных", parse_mode="Markdown")

# ========== ОБРАБОТКА ФОТО (ОСНОВНАЯ) ==========
@dp.message(lambda message: message.photo)
async def handle_photo(message: Message):
    user_id = message.from_user.id
    
    # Проверяем режим ожидания фото
    if user_id not in users_data:
        create_new_user(user_id)
    
    if not users_data[user_id].get("waiting_for_photo"):
        await message.answer(
            "📸 **Фото не добавлено**\n\n"
            "Сначала нажми 'Добавить фото' в меню\n"
            "Или используй команду `/addphoto`",
            parse_mode="Markdown"
        )
        return
    
    # Сохраняем фото
    success, photo_info = await save_photo(user_id, message)
    
    if success:
        users_data[user_id]["message_groups"].append(photo_info)
        save_users()
        
        caption = message.caption or "без подписи"
        total = len(users_data[user_id]["message_groups"])
        
        await message.answer(
            f"✅ **Фото добавлено в очередь!**\n\n"
            f"📸 Подпись: {caption[:50]}\n"
            f"📊 Всего сообщений: {total}\n\n"
            f"💡 Можно отправить еще фото\n"
            f"💡 Чтобы выйти - /cancel",
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            "❌ **Не удалось сохранить фото**\n\n"
            "Попробуй еще раз",
            parse_mode="Markdown"
        )

# ========== ЛОГИН КОМАНДЫ ==========
@dp.message(Command("login"))
async def cmd_login(message: Message):
    user_id = message.from_user.id
    phone = message.text.replace("/login", "").strip()
    
    if not phone or not phone.startswith("+"):
        await message.answer("❌ Формат: `/login +71234567890`", parse_mode="Markdown")
        return
    
    if user_id in users_data and users_data[user_id].get("client"):
        await message.answer("❌ Ты уже авторизован! Используй /logout", parse_mode="Markdown")
        return
    
    try:
        session_name = f"user_{user_id}_{phone.replace('+', '')}"
        client = TelegramClient(session_name, API_ID, API_HASH)
        await client.connect()
        await client.send_code_request(phone)
        
        pending_auth[user_id] = {
            "step": "waiting_code",
            "client": client,
            "phone": phone,
            "session_name": session_name
        }
        
        await message.answer(
            f"📱 **Код отправлен на {phone}**\n\n"
            f"Отправь код: `/code 1#2#3#4#5`",
            parse_mode="Markdown"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}", parse_mode="Markdown")

@dp.message(Command("code"))
async def cmd_code(message: Message):
    user_id = message.from_user.id
    raw_code = message.text.replace("/code", "").strip()
    
    if user_id not in pending_auth:
        await message.answer("❌ Сначала /login", parse_mode="Markdown")
        return
    
    auth_data = pending_auth[user_id]
    code = decode_code(raw_code)
    
    if not code or len(code) < 4:
        await message.answer("❌ Не могу распознать код", parse_mode="Markdown")
        return
    
    await message.answer(f"🔍 Код: `{code}`\n⏳ Вход...", parse_mode="Markdown")
    
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
        
        await message.answer(
            f"✅ **Успешный вход!**\n\n"
            f"📱 Аккаунт: {phone}\n\n"
            f"Теперь настрой рассылку!",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    except errors.SessionPasswordNeededError:
        pending_auth[user_id]["step"] = "need_password"
        await message.answer("🔐 **Нужен 2FA пароль!**\nОтправь: `/password ПАРОЛЬ`", parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}", parse_mode="Markdown")

@dp.message(Command("password"))
async def cmd_password(message: Message):
    user_id = message.from_user.id
    password = message.text.replace("/password", "").strip()
    
    if user_id not in pending_auth:
        await message.answer("❌ Сначала /login", parse_mode="Markdown")
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
        
        await message.answer(
            f"✅ **Успешный вход!**\n\n"
            f"📱 Аккаунт: {phone}",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}", parse_mode="Markdown")

@dp.message(Command("logout"))
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
            "phone": None,
            "client": None,
            "running": False,
            "targets": [],
            "message_groups": [],
            "delay_min": 5,
            "delay_max": 10,
            "task": None,
            "monitor_task": None,
            "temp_photos": []
        }
        save_users()
        await message.answer("🚪 **Вышел из аккаунта**", parse_mode="Markdown")
    else:
        await message.answer("❌ Не авторизован", parse_mode="Markdown")

# ========== ЗАПУСК ==========
async def main():
    load_users()
    print("=" * 50)
    print("🤖 БОТ ЗАПУЩЕН НА RAILWAY")
    print("📸 ПОДДЕРЖКА ФОТО АКТИВНА")
    print("=" * 50)
    
    # Восстанавливаем сессии
    for user_id, user in users_data.items():
        if user.get("client"):
            await start_auto_monitoring(user["client"], user_id)
            if user.get("running"):
                user["task"] = asyncio.create_task(send_loop_for_user(user_id))
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
