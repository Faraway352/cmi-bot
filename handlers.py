from aiogram import Bot, types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart, StateFilter, Command
from sqlalchemy import select, func
from datetime import datetime, date

from config import async_session
from models import User, Event, Registration
from states import Registration as RegState, ProfileEdit
from keyboards import (
    phone_keyboard, gender_keyboard, remove_keyboard,
    main_menu_keyboard, profile_menu_keyboard, notify_settings_keyboard,
    events_list_keyboard, event_card_keyboard,
    my_registrations_keyboard, registration_card_keyboard
)
from validators import (
    is_valid_full_name, contains_emoji, is_valid_birthday,
    is_valid_vk_url, is_valid_tg_username, is_valid_email
)

# ---------- Вспомогательные функции ----------
async def get_user(telegram_id: int):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

async def count_registered(event_id: int) -> int:
    async with async_session() as session:
        return await session.scalar(
            select(func.count(Registration.id)).where(
                Registration.events_id == event_id,
                Registration.status == 'registered'
            )
        )

async def promote_queue(event_id: int, bot: Bot):
    async with async_session() as session:
        first = await session.execute(
            select(Registration).where(
                Registration.events_id == event_id,
                Registration.status == 'waiting'
            ).order_by(Registration.queue_position).limit(1)
        )
        first = first.scalar_one_or_none()
        if not first:
            return
        first.status = 'registered'
        first.queue_position = 0
        user = await session.get(User, first.user_id)
        if user:
            try:
                await bot.send_message(user.telegram_id, "🎉 Освободилось место! Вы автоматически записаны.")
            except Exception:
                pass
        remaining = await session.execute(
            select(Registration).where(
                Registration.events_id == event_id,
                Registration.status == 'waiting'
            ).order_by(Registration.queue_position)
        )
        for i, reg in enumerate(remaining.scalars().all(), start=1):
            reg.queue_position = i
        await session.commit()

async def cancel_registration(event_id: int, user_id: int, bot: Bot):
    async with async_session() as session:
        reg = await session.execute(
            select(Registration).where(
                Registration.user_id == user_id,
                Registration.events_id == event_id,
                Registration.status.in_(['registered', 'waiting'])
            )
        )
        reg = reg.scalar_one_or_none()
        if not reg:
            return False
        old_status = reg.status
        reg.status = 'cancelled'
        await session.commit()
        if old_status == 'registered':
            await promote_queue(event_id, bot)
        return True

# ---------- /start ----------
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user = await get_user(message.from_user.id)
    if user:
        await message.answer(f"С возвращением, {user.full_name}!\nЧто хотите сделать?", reply_markup=main_menu_keyboard())
    else:
        await message.answer(
            "Добро пожаловать! 👋 Я здесь, чтобы вам помочь.\n\n"
            "Я бот, который поможет вам с любой информацией о нашем центре.\n"
            "Хотите узнать о мероприятиях или записаться на них?\n\n"
            "Давайте начнем!",
            reply_markup=remove_keyboard()
        )
        await message.answer("📱 Пожалуйста, предоставьте ваш номер телефона.", reply_markup=phone_keyboard())
        await state.set_state(RegState.waiting_for_phone)

# ---------- Регистрация ----------
async def process_phone_contact(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number
    await state.update_data(phone=phone)
    await message.answer("✅ Номер получен. Введите ваше ФИО (полностью).", reply_markup=remove_keyboard())
    await state.set_state(RegState.waiting_for_full_name)

async def process_phone_manually(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    if not phone.startswith("+") or not phone[1:].isdigit():
        await message.answer("❌ Введите номер в формате +7XXXXXXXXXX или нажмите кнопку ниже.")
        return
    await state.update_data(phone=phone)
    await message.answer("Теперь введите ваше ФИО (полностью).", reply_markup=remove_keyboard())
    await state.set_state(RegState.waiting_for_full_name)

async def process_full_name(message: types.Message, state: FSMContext):
    full_name = message.text.strip()
    if contains_emoji(full_name):
        await message.answer("❌ ФИО не должно содержать эмодзи. Попробуйте ещё раз.")
        return
    if not is_valid_full_name(full_name):
        await message.answer("❌ ФИО должно содержать только буквы и минимум два слова. Попробуйте ещё раз.")
        return
    await state.update_data(full_name=full_name)
    await message.answer("Укажите ваш пол:", reply_markup=gender_keyboard())
    await state.set_state(RegState.waiting_for_gender)

async def process_gender(callback: types.CallbackQuery, state: FSMContext):
    gender = 'Муж' if callback.data == 'gender_male' else 'Жен'
    await state.update_data(gender=gender)
    await callback.message.edit_reply_markup()
    await callback.message.answer("Введите вашу дату рождения в формате ДД.ММ.ГГГГ (например, 01.01.2000):")
    await state.set_state(RegState.waiting_for_birthday)
    await callback.answer()

async def process_birthday(message: types.Message, state: FSMContext):
    birth_text = message.text.strip()
    if not is_valid_birthday(birth_text):
        await message.answer("Не похоже на дату рождения. Попробуйте ещё раз.")
        return
    day, month, year = map(int, birth_text.split("."))
    b_date = date(year, month, day)
    data = await state.get_data()
    async with async_session() as session:
        new_user = User(
            telegram_id=message.from_user.id,
            phone=data.get('phone'),
            full_name=data.get('full_name'),
            gender=data.get('gender'),
            birthday=b_date,
            role='user'
        )
        session.add(new_user)
        await session.commit()
    await message.answer(
        f"🎉 Регистрация завершена!\n\n"
        f"ФИО: {data['full_name']}\nПол: {data['gender']}\n"
        f"Дата рождения: {b_date.strftime('%d.%m.%Y')}\n\nДобро пожаловать!",
        reply_markup=main_menu_keyboard()
    )
    await state.clear()

# ---------- Главное меню ----------
async def main_menu_handler(message: types.Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return
    text = message.text.strip()
    if text == "👤 Личный кабинет":
        await show_profile(message, user)
    elif text == "📋 Мои записи":
        await my_registrations(message)
    elif text == "🎉 Афиша":
        await show_events(message)
    elif text == "💬 Оставить отзыв":
        await message.answer("💬 Здесь можно будет оставить отзыв. Раздел в разработке.")
    else:
        await message.answer("Используйте кнопки меню.")

# ---------- Профиль ----------
async def show_profile(message_or_callback, user):
    vk = user.vk_url or "не указана"
    tg = f"@{user.tg_username}" if user.tg_username else "не указан"
    email = user.email or "не указана"
    text = (
        f"👤 **Личный кабинет**\n\n"
        f"📛 Имя: {user.full_name}\n📞 Телефон: {user.phone}\n"
        f"⚤ Пол: {user.gender}\n🎂 Дата рождения: {user.birthday.strftime('%d.%m.%Y') if user.birthday else 'не указана'}\n"
        f"🔗 VK: {vk}\n💬 Telegram: {tg}\n✉️ Email: {email}\n"
    )
    if isinstance(message_or_callback, types.Message):
        await message_or_callback.answer(text, reply_markup=profile_menu_keyboard(), parse_mode="Markdown")
    else:
        await message_or_callback.message.edit_text(text, reply_markup=profile_menu_keyboard(), parse_mode="Markdown")

async def process_callback_main_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_user(callback.from_user.id)
    if user:
        await callback.message.answer("Главное меню:", reply_markup=main_menu_keyboard())
    else:
        await callback.message.answer("Сначала /start")
    await callback.answer()

async def profile_menu_handler(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала /start")
        return
    if action == "main_menu":
        await process_callback_main_menu(callback, state)
    elif action == "edit_full_name":
        await callback.message.answer("Введите новое ФИО:")
        await state.set_state(ProfileEdit.waiting_for_full_name)
    elif action == "edit_phone":
        await callback.message.answer("Введите новый номер телефона в формате +7XXXXXXXXXX:")
        await state.set_state(ProfileEdit.waiting_for_phone)
    elif action == "edit_gender":
        await callback.message.answer("Выберите пол:", reply_markup=gender_keyboard())
        await state.set_state(ProfileEdit.waiting_for_gender)
    elif action == "edit_birthday":
        await callback.message.answer("Введите новую дату рождения в формате ДД.ММ.ГГГГ:")
        await state.set_state(ProfileEdit.waiting_for_birthday)
    elif action == "edit_vk":
        await callback.message.answer("Введите ссылку на VK (например, https://vk.com/id123456789):")
        await state.set_state(ProfileEdit.waiting_for_vk)
    elif action == "edit_tg_username":
        await callback.message.answer("Введите Telegram username (с @ или без):")
        await state.set_state(ProfileEdit.waiting_for_tg_username)
    elif action == "edit_email":
        await callback.message.answer("Введите ваш email:")
        await state.set_state(ProfileEdit.waiting_for_email)
    elif action == "notify_settings":
        await callback.message.edit_text("🔔 Настройки уведомлений (в разработке).", reply_markup=notify_settings_keyboard())
    elif action == "toggle_notify":
        await callback.answer("Раздел в разработке", show_alert=True)
    elif action == "profile_menu":
        await show_profile(callback, user)
    await callback.answer()

# ---------- Редактирование полей профиля ----------
async def edit_full_name(message: types.Message, state: FSMContext):
    full_name = message.text.strip()
    if not is_valid_full_name(full_name):
        await message.answer("❌ Некорректное ФИО. Попробуйте ещё раз.")
        return
    user = await get_user(message.from_user.id)
    async with async_session() as session:
        user = await session.merge(user)
        user.full_name = full_name
        await session.commit()
    await message.answer("✅ Имя обновлено.")
    await show_profile(message, user)
    await state.clear()

async def edit_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    if not phone.startswith("+") or not phone[1:].isdigit():
        await message.answer("❌ Введите номер в формате +7XXXXXXXXXX.")
        return
    user = await get_user(message.from_user.id)
    async with async_session() as session:
        user = await session.merge(user)
        user.phone = phone
        await session.commit()
    await message.answer("✅ Телефон обновлён.")
    await show_profile(message, user)
    await state.clear()

async def edit_gender_callback(callback: types.CallbackQuery, state: FSMContext):
    gender = 'Муж' if callback.data == 'gender_male' else 'Жен'
    user = await get_user(callback.from_user.id)
    async with async_session() as session:
        user = await session.merge(user)
        user.gender = gender
        await session.commit()
    await callback.message.edit_reply_markup()
    await callback.message.answer("✅ Пол обновлён.")
    await show_profile(callback.message, user)
    await state.clear()
    await callback.answer()

async def edit_birthday(message: types.Message, state: FSMContext):
    birth_text = message.text.strip()
    if not is_valid_birthday(birth_text):
        await message.answer("❌ Некорректная дата. Попробуйте ещё раз.")
        return
    day, month, year = map(int, birth_text.split("."))
    b_date = date(year, month, day)
    user = await get_user(message.from_user.id)
    async with async_session() as session:
        user = await session.merge(user)
        user.birthday = b_date
        await session.commit()
    await message.answer("✅ Дата рождения обновлена.")
    await show_profile(message, user)
    await state.clear()

async def edit_vk(message: types.Message, state: FSMContext):
    vk_url = message.text.strip()
    if not is_valid_vk_url(vk_url):
        await message.answer("❌ Некорректная ссылка VK. Пожалуйста, укажите ссылку вида https://vk.com/id...")
        return
    user = await get_user(message.from_user.id)
    async with async_session() as session:
        user = await session.merge(user)
        user.vk_url = vk_url
        await session.commit()
    await message.answer("✅ Ссылка VK обновлена.")
    await show_profile(message, user)
    await state.clear()

async def edit_tg_username(message: types.Message, state: FSMContext):
    username = message.text.strip()
    if not is_valid_tg_username(username):
        await message.answer("❌ Некорректный username. Используйте формат @example или example (5-32 символов, буквы, цифры, _).")
        return
    if username.startswith('@'):
        username = username[1:]
    user = await get_user(message.from_user.id)
    async with async_session() as session:
        user = await session.merge(user)
        user.tg_username = username
        await session.commit()
    await message.answer("✅ Telegram username обновлён.")
    await show_profile(message, user)
    await state.clear()

async def edit_email(message: types.Message, state: FSMContext):
    email = message.text.strip()
    if not is_valid_email(email):
        await message.answer("❌ Некорректный email. Попробуйте ещё раз.")
        return
    user = await get_user(message.from_user.id)
    async with async_session() as session:
        user = await session.merge(user)
        user.email = email
        await session.commit()
    await message.answer("✅ Email обновлён.")
    await show_profile(message, user)
    await state.clear()

# ================== АФИША ==================
async def show_events(message_or_callback):
    async with async_session() as session:
        stmt = select(Event).where(Event.date_time > func.now(), Event.status == 'active', Event.is_archived == False).order_by(Event.date_time).limit(4)
        events = (await session.execute(stmt)).scalars().all()
    if not events:
        text = "😔 На данный момент нет актуальных мероприятий."
        if isinstance(message_or_callback, types.Message):
            await message_or_callback.answer(text)
        else:
            await message_or_callback.message.edit_text(text)
        return
    lines = ["🎉 **Ближайшие мероприятия**\n"]
    for ev in events:
        regs = await count_registered(ev.id)
        limit = ev.participants_limit if ev.participants_limit else "∞"
        lines.append(f"• **{ev.title}** — {ev.date_time.strftime('%d.%m в %H:%M')} — Мест: {regs} из {limit}")
    text = "\n".join(lines)
    keyboard = events_list_keyboard(events)
    if isinstance(message_or_callback, types.Message):
        await message_or_callback.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message_or_callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def event_detail(callback: types.CallbackQuery):
    event_id = int(callback.data.split("_")[1])
    async with async_session() as session:
        event = await session.get(Event, event_id)
    if not event:
        await callback.answer("Мероприятие не найдено.", show_alert=True)
        return
    user = await get_user(callback.from_user.id)
    async with async_session() as session:
        reg = await session.execute(select(Registration).where(
            Registration.user_id == user.id, Registration.events_id == event_id, Registration.status.in_(['registered', 'waiting'])
        ))
        reg = reg.scalar_one_or_none()
    is_registered = reg is not None
    can_register = True
    if event.participants_limit:
        if await count_registered(event.id) >= event.participants_limit:
            can_register = False
    text = (
        f"**{event.title}**\n📅 {event.date_time.strftime('%d.%m.%Y в %H:%M')}\n"
        f"📍 {event.location or 'Не указано'}\n💰 {'Платное' if event.is_paid else 'Бесплатное'}\n"
        f"{event.description or ''}\n"
    )
    if event.participants_limit:
        text += f"📌 Мест: {await count_registered(event.id)} из {event.participants_limit}\n"
    await callback.message.edit_text(text, reply_markup=event_card_keyboard(event.id, is_registered, can_register), parse_mode="Markdown")
    await callback.answer()

async def register_for_event(callback: types.CallbackQuery):
    event_id = int(callback.data.split("_")[1])
    user = await get_user(callback.from_user.id)
    async with async_session() as session:
        existing = await session.execute(select(Registration).where(
            Registration.user_id == user.id, Registration.events_id == event_id, Registration.status.in_(['registered', 'waiting'])
        ))
        if existing.scalar_one_or_none():
            await callback.answer("Вы уже записаны или в очереди.", show_alert=True)
            return
        event = await session.get(Event, event_id)
        if not event or event.status != 'active':
            await callback.answer("Мероприятие неактивно.", show_alert=True)
            return
        regs = await count_registered(event.id)
        if event.participants_limit and regs >= event.participants_limit:
            max_q = await session.scalar(select(func.max(Registration.queue_position)).where(
                Registration.events_id == event_id, Registration.status == 'waiting'
            ))
            new_pos = (max_q or 0) + 1
            session.add(Registration(user_id=user.id, events_id=event_id, status='waiting', queue_position=new_pos))
            await session.commit()
            await callback.answer("Добавлены в очередь.", show_alert=True)
        else:
            session.add(Registration(user_id=user.id, events_id=event_id, status='registered'))
            await session.commit()
            await callback.answer("Вы записаны!", show_alert=True)
    await event_detail(callback)

async def cancel_reg_handler(callback: types.CallbackQuery, bot: Bot):
    event_id = int(callback.data.split("_")[2])
    user = await get_user(callback.from_user.id)
    success = await cancel_registration(event_id, user.id, bot)
    if success:
        await callback.answer("Запись отменена.")
        await event_detail(callback)
    else:
        await callback.answer("Не удалось отменить запись.", show_alert=True)

# ================== МОИ ЗАПИСИ ==================
async def my_registrations(message_or_callback):
    user = await get_user(message_or_callback.from_user.id)
    async with async_session() as session:
        regs = await session.execute(
            select(Registration).where(
                Registration.user_id == user.id, Registration.status.in_(['registered', 'waiting'])
            ).order_by(Registration.created_at.desc())
        )
        regs = regs.scalars().all()
        for reg in regs:
            await session.refresh(reg, ['event'])
    if not regs:
        text = "У вас пока нет записей."
        if isinstance(message_or_callback, types.Message):
            await message_or_callback.answer(text)
        else:
            await message_or_callback.message.edit_text(text)
        return
    text = "📋 **Ваши записи**\n"
    keyboard = my_registrations_keyboard(regs)
    if isinstance(message_or_callback, types.Message):
        await message_or_callback.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message_or_callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def my_registration_detail(callback: types.CallbackQuery):
    reg_id = int(callback.data.split("_")[1])
    async with async_session() as session:
        reg = await session.get(Registration, reg_id)
        if not reg:
            await callback.answer("Запись не найдена.")
            return
        await session.refresh(reg, ['event'])
        event = reg.event
        can_cancel = reg.status in ('registered', 'waiting') and event.date_time > datetime.now()
    text = (
        f"**{event.title}**\n📅 {event.date_time.strftime('%d.%m.%Y в %H:%M')}\n"
        f"📍 {event.location or 'Не указано'}\n"
        f"Статус: {'✅ Записан' if reg.status == 'registered' else '🕒 В очереди'}\n"
    )
    if reg.status == 'waiting':
        text += f"Позиция в очереди: {reg.queue_position}\n"
    await callback.message.edit_text(text, reply_markup=registration_card_keyboard(reg.id, event.id, can_cancel), parse_mode="Markdown")
    await callback.answer()

# ================== Команда /seed ==================
async def cmd_seed(message: types.Message):
    user = await get_user(message.from_user.id)
    if not user or user.role != 'admin':
        await message.answer("⛔ Недостаточно прав.")
        return
    test_events = [
        {"title": "Квиз «Молодежь и наука»", "description": "Интеллектуальная игра для студентов.", "date_time": datetime(2026, 6, 15, 18, 0), "location": "ул. Ленина, 10", "participants_limit": 20, "is_paid": False},
        {"title": "Мастер-класс по SMM", "description": "Практический семинар.", "date_time": datetime(2026, 7, 1, 15, 0), "location": "Центр молодежных инициатив", "participants_limit": 15, "is_paid": True},
        {"title": "Велопробег «Вперед!»", "description": "Спортивный заезд.", "date_time": datetime(2026, 8, 20, 10, 0), "location": "Старт от площади Ленина", "participants_limit": 0, "is_paid": False}
    ]
    async with async_session() as session:
        for ev in test_events:
            session.add(Event(**ev))
        await session.commit()
    await message.answer("✅ Тестовые мероприятия созданы.")

# ---------- /menu ----------
async def cmd_menu(message: types.Message):
    user = await get_user(message.from_user.id)
    if user:
        await message.answer("Главное меню:", reply_markup=main_menu_keyboard())
    else:
        await message.answer("Сначала /start")

# ---------- Эхо ----------
async def echo(message: types.Message):
    await message.answer("Используйте /start или кнопки меню.")
