import asyncio
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, StateFilter, Command
from aiogram.types import BotCommand

from config import BOT_TOKEN, engine
from models import Base
from states import Registration, ProfileEdit
from handlers import (
    cmd_start,
    process_phone_contact,
    process_phone_manually,
    process_full_name,
    process_gender,
    process_birthday,
    main_menu_handler,
    profile_menu_handler,
    process_callback_main_menu,
    edit_full_name,
    edit_phone,
    edit_gender_callback,
    edit_birthday,
    edit_vk,
    cmd_menu,
    echo,
)

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

    dp.message.register(main_menu_handler, F.text.in_([
        "👤 Личный кабинет", "📋 Мои записи", "🎉 Афиша", "💬 Оставить отзыв"
    ]))

    dp.callback_query.register(profile_menu_handler, F.data.in_([
        "edit_full_name", "edit_phone", "edit_gender", "edit_birthday",
        "edit_vk", "notify_settings", "profile_menu", "main_menu", "toggle_notify"
    ]))

    dp.message.register(edit_full_name, ProfileEdit.waiting_for_full_name)
    dp.message.register(edit_phone, ProfileEdit.waiting_for_phone)
    dp.callback_query.register(edit_gender_callback, ProfileEdit.waiting_for_gender, F.data.startswith('gender_'))
    dp.message.register(edit_birthday, ProfileEdit.waiting_for_birthday)
    dp.message.register(edit_vk, ProfileEdit.waiting_for_vk)

    dp.message.register(cmd_menu, Command("menu"))
    dp.message.register(echo, StateFilter(None))

    # ===== ВРЕМЕННО: сброс всех таблиц перед созданием =====
    # УДАЛИТЬ после первого успешного деплоя!
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        print("=== Old tables dropped ===")
    # ===== КОНЕЦ ВРЕМЕННОГО БЛОКА =====

    # Создаём таблицы заново
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await bot.set_my_commands([
        BotCommand(command="start", description="Начать/перезапустить"),
        BotCommand(command="menu", description="Открыть главное меню")
    ])

    await asyncio.gather(
        run_web_server(),
        dp.start_polling(bot)
    )

if __name__ == '__main__':
    asyncio.run(main())
