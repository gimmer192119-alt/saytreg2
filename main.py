from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncio

API_ID = 1052214432  # Ваш API ID
API_HASH = "ebaeb06fb466d299884ab73e34cc228b"

app = Client("my_account", api_id=API_ID, api_hash=API_HASH)

settings = {}

@app.on_message(filters.command("start") & filters.me)
async def start(client, message):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Настроить группу", callback_data="setup")],
        [InlineKeyboardButton("🚀 Старт", callback_data="start_post")],
        [InlineKeyboardButton("⏹ Стоп", callback_data="stop_post")]
    ])
    await message.reply("Userbot готов. Выберите действие:", reply_markup=kb)

@app.on_callback_query(filters.regex("setup"))
async def setup(client, callback_query):
    await callback_query.message.reply("📝 Отправьте ссылку на группу или ID:")
    
    @app.on_message(filters.me & filters.text & ~filters.command(["start"]))
    async def save_group(client, msg):
        settings['group'] = msg.text
        await msg.reply("✅ Группа сохранена. Теперь отправьте сообщение для рассылки (можно с фото):")
        
        @app.on_message(filters.me & (filters.text | filters.photo))
        async def save_message(client, m):
            settings['text'] = m.text or m.caption or ""
            settings['photo'] = m.photo.file_id if m.photo else None
            await m.reply("⏱ Введите интервал в секундах (рекомендую 60+):")
            
            @app.on_message(filters.me & filters.text)
            async def save_interval(client, interval_msg):
                settings['interval'] = int(interval_msg.text)
                settings['ready'] = True
                await interval_msg.reply(f"✅ Готово! Интервал: {settings['interval']} сек. Нажмите 🚀 для запуска.")

@app.on_callback_query(filters.regex("start_post"))
async def start_posting(client, callback_query):
    if not settings.get('ready'):
        await callback_query.answer("Сначала настройте через ⚙️", show_alert=True)
        return
    
    settings['active'] = True
    asyncio.create_task(posting_loop(client))
    await callback_query.answer("🚀 Запущено!")

async def posting_loop(client):
    while settings.get('active'):
        try:
            if settings.get('photo'):
                await client.send_photo(settings['group'], settings['photo'], caption=settings['text'])
            else:
                await client.send_message(settings['group'], settings['text'])
            await asyncio.sleep(settings['interval'])
        except Exception as e:
            print(f"Ошибка: {e}")
            settings['active'] = False

@app.on_callback_query(filters.regex("stop_post"))
async def stop_posting(client, callback_query):
    settings['active'] = False
    await callback_query.answer("⏹ Остановлено")

app.run()
