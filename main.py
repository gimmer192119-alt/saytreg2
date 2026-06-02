import asyncio
import logging
import random
import string
import urllib.parse
import aiohttp
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message

# ================= НАСТРОЙКИ =================
BOT_TOKEN = "8628009037:AAEM-kEYQ1hcOHF7IAwr3Qm4XH3Li7Ejlfo" # <-- Вставь сюда токен своего бота

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
            # Пароль для самого почтового ящика (нужен для входа и чтения писем)
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

# ================= ПРОЦЕСС РЕГИСТРАЦИИ =================
async def register_account(ref_code: str):
    email, mail_pass, status = await create_temp_email()
    if not email:
        return None, f"❌ Не удалось создать почту: {status}"
        
    # Генерация логина и пароля (под твой формат из CURL)
    login = ''.join(random.choices(string.digits, k=6))
    password = "Derver" + ''.join(random.choices(string.digits, k=6))
    
    # Куки с реферальным ID
    cookies = {"referral_id": ref_code}
    
    # Заголовки для первого шага (GET)
    headers_get = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive",
        "Referer": "https://twiboost.com/",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
    }
    
    try:
        async with aiohttp.ClientSession(cookies=cookies) as session:
            # ШАГ 1: Заходим на страницу регистрации, чтобы получить XSRF-TOKEN в куки
            async with session.get("https://twiboost.com/reg", headers=headers_get) as resp:
                pass
                
            # Достаем токен из кук
            xsrf_cookie = session.cookie_jar.filter_cookies("https://twiboost.com").get("XSRF-TOKEN")
            if not xsrf_cookie:
                return None, "❌ Не удалось получить XSRF-TOKEN (сайт изменил защиту?)."
                
            # Токен в куках обычно URL-encoded, декодируем его
            token_val = urllib.parse.unquote(xsrf_cookie.value)
            
            # Заголовки для второго шага (POST)
            headers_post = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                "Content-Type": "application/json",
                "X-Site-Host": "twiboost.com",
                "X-XSRF-TOKEN": token_val,
                "Origin": "https://twiboost.com",
                "Connection": "keep-alive",
                "Referer": "https://twiboost.com/reg",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            }
            
            payload = {
                "login": login,
                "email": email,
                "password": password
            }
            
            # ШАГ 2: Отправляем данные на API регистрации
            async with session.post("https://twiboost.com/api/register", json=payload, headers=headers_post) as resp:
                result = await resp.text()
                
                # Возвращаем данные, включая пароль от временной почты
                account_data = {
                    "twiboost_email": email,
                    "mailbox_password": mail_pass, # <-- Пароль от самой почты
                    "twiboost_login": login,
                    "twiboost_password": password,
                    "response": result
                }
                return account_data, "Success"
                
    except Exception as e:
        logging.error(f"Ошибка сети при регистрации: {e}")
        return None, f"❌ Сетевая ошибка: {e}"

# ================= ХЕНДЛЕРЫ БОТА =================
@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Привет! Я бот для авторега на twiboost.com.\n"
        "🛡️ *Почта:* Теперь используется надежный сервис `mail.tm`.\n\n"
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
    await message.answer(f"⚙️ *Настройки:*\nРеф. код: `{SETTINGS['ref_code']}`\nАвторежим: {status}", parse_mode="Markdown")

@router.message(Command("setref"))
async def cmd_setref(message: Message):
    args = message.text.split()
    if len(args) > 1:
        SETTINGS["ref_code"] = args[1]
        await message.answer(f"✅ Реферальный код обновлен на: `{SETTINGS['ref_code']}`", parse_mode="Markdown")
    else:
        await message.answer("⚠️ Использование: `/setref 3720781`", parse_mode="Markdown")

@router.message(Command("test"))
async def cmd_test(message: Message):
    wait_msg = await message.answer("⏳ Генерирую надежную почту и запускаю тестовую регистрацию...")
    data, status = await register_account(SETTINGS["ref_code"])
    
    if status == "Success":
        await wait_msg.edit_text(
            f"✅ *Регистрация успешна!*\n\n"
            f"📦 *Данные от Twiboost:*\n"
            f"📧 Email: `{data['twiboost_email']}`\n"
            f"👤 Login: `{data['twiboost_login']}`\n"
            f"🔑 Password: `{data['twiboost_password']}`\n\n"
            f"📬 *Данные от временной почты (для подтверждения):*\n"
            f"🔗 Сайт: `https://mail.tm`\n"
            f"🔑 Mail Pass: `{data['mailbox_password']}`\n\n"
            f"📦 *Ответ сервера:*\n`{data['response'][:200]}`", parse_mode="Markdown"
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
        print(">>> 2. Библиотеки на месте. Подключаюсь к Telegram...")
        
        logging.basicConfig(level=logging.INFO)
        asyncio.run(main())
        
        print(">>> 3. Бот остановлен (этого не должно происходить так быстро).")
    except Exception as e:
        print("\n" + "="*50)
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {type(e).__name__}")
        print(f"📝 ПРИЧИНА: {e}")
        print("="*50 + "\n")
    finally:
        input("⏸️ Нажмите Enter, чтобы закрыть окно...")