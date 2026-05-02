import asyncio
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, StateFilter
from aiogram.types import BotCommand

from config import BOT_TOKEN, engine
from models import Base
from states import Registration
from handlers import (
    cmd_start,
    process_phone_contact,
    process_phone_manually,
    process_full_name,
    process_gender,
    process_birthday,
    echo,
)

# Health check endpoint для Render и UptimeRobot
async def healthcheck(request):
    return web.Response(text="OK")

async def run_web_server():
    app = web.Application()
    app.router.add_get("/", healthcheck)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    print(f"Health check server started on port {port}")

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Регистрация обработчиков
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(process_phone_contact, Registration.waiting_for_phone, F.contact)
    dp.message.register(process_phone_manually, Registration.waiting_for_phone)
    dp.message.register(process_full_name, Registration.waiting_for_full_name)
    dp.callback_query.register(process_gender, Registration.waiting_for_gender, F.data.startswith('gender_'))
    dp.message.register(process_birthday, Registration.waiting_for_birthday)
    dp.message.register(echo, StateFilter(None))

    # Создаём таблицы в БД
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Устанавливаем аватарку бота (прямой запрос к API)
    try:
        with open("ava.png", "rb") as photo:
            await bot.request("setMyPhoto", {"photo": photo})
        print("Аватарка обновлена")
    except Exception as e:
        print(f"Не удалось установить аватарку: {e}")

    # Команды бота
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать/перезапустить")
    ])

    # Запуск веб-сервера и поллинга
    await asyncio.gather(
        run_web_server(),
        dp.start_polling(bot)
    )

if __name__ == '__main__':
    asyncio.run(main())
