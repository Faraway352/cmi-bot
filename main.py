import asyncio
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
    process_first_name,
    process_last_name,
    process_gender,
    process_birth_date,
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
    # Render передаёт порт в переменной окружения PORT, иначе используем 8080
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    print(f"Health check server started on port {port}")

async def on_startup():
    # Создаём таблицы в БД
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    bot = Bot.get_current()
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать/перезапустить")
    ])

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp["bot"] = bot

    # Регистрируем хендлеры
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(process_phone_contact, Registration.waiting_for_phone, F.contact)
    dp.message.register(process_phone_manually, Registration.waiting_for_phone)
    dp.message.register(process_first_name, Registration.waiting_for_first_name)
    dp.message.register(process_last_name, Registration.waiting_for_last_name)
    dp.callback_query.register(process_gender, Registration.waiting_for_gender, F.data.startswith('gender_'))
    dp.message.register(process_birth_date, Registration.waiting_for_birth_date)
    dp.message.register(echo, StateFilter(None))

    await on_startup()

    # Запускаем веб-сервер и поллинг параллельно
    await asyncio.gather(
        run_web_server(),
        dp.start_polling(bot)
    )

if __name__ == '__main__':
    import os
    asyncio.run(main())
