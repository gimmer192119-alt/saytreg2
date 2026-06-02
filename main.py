import asyncio
import logging
import random
import string
import re
import urllib.parse
from curl_cffi.requests import AsyncSession
import aiohttp
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message

# ================= НАСТРОЙКИ =================
# ⚠️ ВНИМАНИЕ: Твой старый токен засветился в чате! 
# Обязательно зайди в @BotFather -> /revoke и вставь НОВЫЙ токен сюда:
BOT_TOKEN = "ВСТАВЬ_СЮДА_НОВЫЙ_ТОКЕН"

# Глобальные настройки (хранятся в памяти)
SETTINGS = {
    "ref_code": "3720781",
    "auto_mode": False,
    "auto_task": None
}

router = Router()

# ================= НАДЕЖНАЯ ГЕНЕРАЦИЯ ПОЧТЫ (MAIL.TM) =================
async def create_temp_email():
    """
    Создание надежной временной почты через сервис mail.tm
    Возвращает: (email, password_to_mailbox, status)
    """
    domains_url = "https://api.mail.tm/domains"
    accounts_url = "https://api.mail.tm/accounts"
    
    headers = {"Accept": "application/ld+json"}
    
    try:
        async with aiohttp.ClientSession() as session:
            # 1. Получаем список активных доменов
            async with session.get(domains_url, headers=headers) as resp:
                if resp.status != 200:
                    return None, None, f"Ошибка получения доменов: {resp.status}"
                data = await resp.json()
                
                # Ищем первый активный домен
                domain = None
                for item in data.get("hydra:member", []):
                    if item.get("isActive"):
                        domain = item.get("domain")
                        break
                        
                if not domain:
                    return None, None, "Нет доступных активных доменов"
            
            # 2. Генерируем случайные данные для ящика
            login = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
            mail_password = ''.join(random.choices(string.ascii_letters + string.digits, k=14))
            address = f"{login}@{domain}"
            
            # 3. Регистрируем ящик на mail.tm
            payload = {"address": address, "password": mail_password}
            create_headers = {"Accept": "application/json", "Content-Type": "application/json"}
            
            async with session.post(accounts_url, json=payload, headers=create_headers) as resp:
                if resp.status in [200, 201]:
                    return address, mail_password, "Success"
                else:
                    error_text = await resp.text()
                    return None, None, f"Ошибка создания ящика: {error_text[:200]}"
                    
    except Exception as e:
        logging.error(f"Ошибка mail.tm: {e}")
        return None, None, f"Сетевая ошибка: {e}"

# ================= ПРОЦЕСС РЕГИСТРАЦИИ (С ОБХОДОМ DATADOME) =================
async def register_account(ref_code: str):
    """
    Регистрация на twiboost.com с обходом защиты Datadome
    Использует curl_cffi для клонирования TLS-отпечатка реального Chrome
    """
    email, mail_pass, status = await create_temp_email()
    if not email:
        return None, f"❌ Не удалось создать почту: {status}"
        
    login = ''.join(random.choices(string.digits, k=6))
    password = "Derver" + ''.join(random.choices(string.digits, k=6))
    
    try:
        # 🛡 Используем curl_cffi - он клонирует TLS-отпечаток реального Chrome 120
        # Для сайта наш запрос неотличим от настоящего браузера
        async with AsyncSession(impersonate="chrome120") as session:
            
            # ШАГ 1: Заходим СРАЗУ по реферальной ссылке
            # Это правильно поставит куку referral_id и "прогреет" сессию
            await session.get(f"https://twiboost.com/ref{ref_code}")
            
            # ШАГ 2: Заходим на страницу регистрации
            resp = await session.get("https://twiboost.com/reg")
            html = resp.text
            
            # 🔍 Ищем CSRF-токен
            token_val = None
            
            # Вариант 1: <meta name="csrf-token" content="...">
            match = re.search(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', html)
            if match:
                token_val = match.group(1)
            
            # Вариант 2: window.Laravel = {"csrfToken":"..."}
            if not token_val:
                match = re.search(r'csrfToken["\s:]+["\']([^"\']+)["\']', html)
                if match:
                    token_val = match.group(1)
                    
            # Вариант 3: <input type="hidden" name="_token" value="...">
            if not token_val:
                match = re.search(r'name="_token"\s+value="([^"]+)"', html)
                if match:
                    token_val = match.group(1)
            
            # Вариант 4: Если в HTML нет — берем из куки XSRF-TOKEN
            if not token_val:
                xsrf = session.cookies.get("XSRF-TOKEN")
                if xsrf:
                    token_val = urllib.parse.unquote(xsrf)
            
            # Если токен так и не нашли — проверяем, показали ли нам форму регистрации
            if not token_val:
                if "Создать аккаунт" not in html and "Пароль" not in html:
                    return None, f"❌ Сайт не показал форму регистрации. Возможно, капча Datadome. HTML:\n\n{html[:400]}"
            
            # ШАГ 3: Отправляем POST-запрос на регистрацию
            headers_post = {
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "X-Site-Host": "twiboost.com",
                "Origin": "https://twiboost.com",
                "Referer": "https://twiboost.com/reg",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            }
            
            # Если токен нашли — добавляем его в заголовок
            if token_val:
                headers_post["X-XSRF-TOKEN"] = token_val
                
            payload = {
                "login": login,
                "email": email,
                "password": password
            }
            
            resp_post = await session.post(
                "https://twiboost.com/api/register", 
                json=payload, 
                headers=headers_post
            )
            result = resp_post.text
            
            account_data = {
                "twiboost_email": email,
                "mailbox_password": mail_pass,
                "twiboost_login": login,
                "twiboost_password": password,
                "response": result
            }
            return account_data, "Success"
            
    except Exception as e:
        logging.error(f"Ошибка curl_cffi: {e}")
        return None, f"❌ Ошибка: {type(e).__name__}: {e}"

# ================= ХЕНДЛЕРЫ БОТА =================
@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Привет! Я бот для авторега на twiboost.com.\n"
        "🛡️ *Почта:* надежный сервис `mail.tm`\n"
        "🛡️ *Защита:* обход Datadome через `curl_cffi`\n\n"
        "📋 *Команды:*\n"
        "/test - Сделать 1 регистрацию для проверки\n"
        "/auto - Запустить авторег (интервал 5-60 мин)\n"
        "/stop - Остановить авторег\n"
        "/setref <код> - Настроить реферальный код\n"
        "/settings - Текущие настройки", parse_mode="Markdown"
    )

@router.message(Command("settings"))
async def cmd_settings(message: Message):
    status = "🟢 Вкл" if SETTINGS["auto_mode"] else "🔴 Выкл"
    await message.answer(
        f"⚙️ *Настройки:*\n"
        f"Реф. код: `{SETTINGS['ref_code']}`\n"
        f"Авторежим: {status}", parse_mode="Markdown"
    )

@router.message(Command("setref"))
async def cmd_setref(message: Message):
    args = message.text.split()
    if len(args) > 1:
        SETTINGS["ref_code"] = args[1]
        await message.answer(
            f"✅ Реферальный код обновлен на: `{SETTINGS['ref_code']}`", 
            parse_mode="Markdown"
        )
    else:
        await message.answer("⚠️ Использование: `/setref 3720781`", parse_mode="Markdown")

@router.message(Command("test"))
async def cmd_test(message: Message):
    wait_msg = await message.answer("⏳ Генерирую почту и запускаю тестовую регистрацию...")
    data, status = await register_account(SETTINGS["ref_code"])
    
    if status == "Success":
        await wait_msg.edit_text(
            f"✅ *Регистрация успешна!*\n\n"
            f"📦 *Данные от Twiboost:*\n"
            f"📧 Email: `{data['twiboost_email']}`\n"
            f"👤 Login: `{data['twiboost_login']}`\n"
            f"🔑 Password: `{data['twiboost_password']}`\n\n"
            f"📬 *Вход во временную почту (mail.tm):*\n"
            f"🔗 Сайт: `https://mail.tm`\n"
            f"🔑 Mail Pass: `{data['mailbox_password']}`\n\n"
            f"📦 *Ответ сервера:*\n`{data['response'][:300]}`", parse_mode="Markdown"
        )
    else:
        await wait_msg.edit_text(f"❌ Ошибка: {status}")

# ================= ЦИКЛ АВТОРЕГИСТРАЦИИ =================
async def auto_registration_loop(bot: Bot, chat_id: int):
    while SETTINGS["auto_mode"]:
        # Рандомный интервал от 5 до 60 минут в секундах
        interval = random.randint(5, 60) * 60 
        mins = interval // 60
        
        await bot.send_message(chat_id, f"⏳ Следующая регистрация через {mins} мин.")
        
        # Ждем, но проверяем флаг каждую секунду, чтобы можно было быстро прервать
        for _ in range(interval):
            if not SETTINGS["auto_mode"]:
                return
            await asyncio.sleep(1)
            
        if not SETTINGS["auto_mode"]:
            break
            
        await bot.send_message(chat_id, "🔄 Выполняю автоматическую регистрацию...")
        data, status = await register_account(SETTINGS["ref_code"])
        
        if status == "Success":
            await bot.send_message(
                chat_id,
                f"✅ *Авто-рег успешен!*\n\n"
                f"📦 *Twiboost:*\n"
                f"📧 `{data['twiboost_email']}`\n"
                f"👤 `{data['twiboost_login']}`\n"
                f"🔑 `{data['twiboost_password']}`\n\n"
                f"📬 *Вход в почту (mail.tm):*\n"
                f"🔑 `{data['mailbox_password']}`", parse_mode="Markdown"
            )
        else:
            await bot.send_message(chat_id, f"❌ Ошибка авто-рега: {status}")

@router.message(Command("auto"))
async def cmd_auto(message: Message, bot: Bot):
    if SETTINGS["auto_mode"]:
        await message.answer("⚠️ Авторегистрация уже запущена!")
        return
        
    SETTINGS["auto_mode"] = True
    await message.answer("🚀 Авторегистрация запущена! (Случайный интервал 5-60 мин)")
    
    # Запускаем фоновую задачу
    SETTINGS["auto_task"] = asyncio.create_task(auto_registration_loop(bot, message.chat.id))

@router.message(Command("stop"))
async def cmd_stop(message: Message):
    if not SETTINGS["auto_mode"]:
        await message.answer("⚠️ Авторегистрация и так выключена.")
        return
        
    SETTINGS["auto_mode"] = False
    if SETTINGS["auto_task"]:
        SETTINGS["auto_task"].cancel()
    await message.answer("🛑 Авторегистрация остановлена.")

# ================= ЗАПУСК =================
async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        print(">>> 1. Скрипт запущен. Проверяю библиотеки...")
        import aiogram
        import aiohttp
        from curl_cffi.requests import AsyncSession
        print(">>> 2. Все библиотеки на месте. Подключаюсь к Telegram...")
        
        logging.basicConfig(level=logging.INFO)
        asyncio.run(main())
        
        print(">>> 3. Бот остановлен.")
    except Exception as e:
        print("\n" + "="*50)
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {type(e).__name__}")
        print(f"📝 ПРИЧИНА: {e}")
        print("="*50 + "\n")
    finally:
        input("⏸️ Нажмите Enter, чтобы закрыть окно...")
