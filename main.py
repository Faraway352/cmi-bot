import asyncio
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, StateFilter, Command
from aiogram.types import BotCommand

from config import BOT_TOKEN, engine
from models import Base
from states import Registration as RegState, ProfileEdit, FeedbackFlow
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
    edit_tg_username,
    edit_email,
    show_events,
    event_detail,
    register_for_event,
    cancel_reg_handler,
    my_registrations,
    my_registration_detail,
    start_feedback,
    feedback_chosen,
    save_feedback,
    cmd_seed,
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

    # Регистрация
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(process_phone_contact, RegState.waiting_for_phone, F.contact)
    dp.message.register(process_phone_manually, RegState.waiting_for_phone)
    dp.message.register(process_full_name, RegState.waiting_for_full_name)
    dp.callback_query.register(process_gender, RegState.waiting_for_gender, F.data.startswith('gender_'))
    dp.message.register(process_birthday, RegState.waiting_for_birthday)

    # Главное меню
    dp.message.register(main_menu_handler, F.text.in_([
        "👤 Личный кабинет", "📋 Мои записи", "🎉 Афиша", "💬 Оставить отзыв"
    ]))

    # Профиль
    dp.callback_query.register(process_callback_main_menu, F.data == "main_menu")
    dp.callback_query.register(profile_menu_handler, F.data.in_([
        "edit_full_name", "edit_phone", "edit_gender", "edit_birthday",
        "edit_vk", "edit_tg_username", "edit_email",
        "notify_settings", "toggle_notify", "profile_menu"
    ]))
    dp.message.register(edit_full_name, ProfileEdit.waiting_for_full_name)
    dp.message.register(edit_phone, ProfileEdit.waiting_for_phone)
    dp.callback_query.register(edit_gender_callback, ProfileEdit.waiting_for_gender, F.data.startswith('gender_'))
    dp.message.register(edit_birthday, ProfileEdit.waiting_for_birthday)
    dp.message.register(edit_vk, ProfileEdit.waiting_for_vk)
    dp.message.register(edit_tg_username, ProfileEdit.waiting_for_tg_username)
    dp.message.register(edit_email, ProfileEdit.waiting_for_email)

    # Афиша
    dp.callback_query.register(show_events, F.data == "show_events")
    dp.callback_query.register(event_detail, F.data.startswith("event_"))
    dp.callback_query.register(register_for_event, F.data.startswith("register_"))
    dp.callback_query.register(cancel_reg_handler, F.data.startswith("cancel_reg_"))

    # Мои записи
    dp.callback_query.register(my_registrations, F.data == "my_registrations")
    dp.callback_query.register(my_registration_detail, F.data.startswith("myreg_"))

    # Отзывы
    dp.callback_query.register(feedback_chosen, F.data.startswith("feedback_"))
    dp.message.register(save_feedback, FeedbackFlow.waiting_for_text)

    # Команды
    dp.message.register(cmd_seed, Command("seed"))
    dp.message.register(cmd_menu, Command("menu"))
    dp.message.register(echo, StateFilter(None))

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await bot.set_my_commands([
        BotCommand(command="start", description="Начать/перезапустить"),
        BotCommand(command="menu", description="Открыть главное меню"),
        BotCommand(command="seed", description="(админ) Создать тестовые мероприятия")
    ])

    await asyncio.gather(
        run_web_server(),
        dp.start_polling(bot)
    )

if __name__ == '__main__':
    asyncio.run(main())
