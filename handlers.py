from aiogram import Bot, types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart, StateFilter, Command
from sqlalchemy import select, func, update
from datetime import datetime, date
import re

from config import async_session
from models import User, Event, Registration, Feedback
from states import (
    Registration as RegState,
    ProfileEdit,
    FeedbackFlow,
    AdminEventCreate,
    AdminEventEdit,
    AdminBroadcast,
)
from keyboards import (
    phone_keyboard,
    gender_keyboard,
    remove_keyboard,
    main_menu_keyboard,
    profile_menu_keyboard,
    notify_settings_keyboard,
    events_list_keyboard,
    event_card_keyboard,
    my_registrations_keyboard,
    registration_card_keyboard,
    feedback_event_keyboard,
    admin_main_keyboard,
    admin_users_keyboard,
    admin_events_keyboard,
    admin_event_manage_keyboard,
    admin_feedbacks_keyboard,
)
from validators import (
    is_valid_full_name,
    contains_emoji,
    is_valid_birthday,
    is_valid_vk_url,
    is_valid_tg_username,
    is_valid_email,
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
                Registration.status == 'registered',
            )
        )

async def promote_queue(event_id: int, bot: Bot):
    async with async_session() as session:
        first = await session.execute(
            select(Registration)
            .where(
                Registration.events_id == event_id,
                Registration.status == 'waiting',
            )
            .order_by(Registration.queue_position)
            .limit(1)
        )
        first = first.scalar_one_or_none()
        if not first:
            return
        first.status = 'registered'
        first.queue_position = 0
        user = await session.get(User, first.user_id)
        if user:
            try:
                await bot.send_message(
                    user.telegram_id,
                    "🎉 Освободилось место! Вы автоматически записаны.",
                )
            except Exception:
                pass
        remaining = await session.execute(
            select(Registration)
            .where(
                Registration.events_id == event_id,
                Registration.status == 'waiting',
            )
            .order_by(Registration.queue_position)
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
                Registration.status.in_(['registered', 'waiting']),
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
        is_admin = user.role == 'admin'
        await message.answer(
            f"С возвращением, {user.full_name}!\nЧто хотите сделать?",
            reply_markup=main_menu_keyboard(is_admin),
        )
    else:
        await message.answer(
            "Добро пожаловать! 👋 Я здесь, чтобы вам помочь.\n\n"
            "Я бот, который поможет вам с любой информацией о нашем центре.\n"
            "Хотите узнать о мероприятиях или записаться на них?\n\n"
            "Давайте начнем!",
            reply_markup=remove_keyboard(),
        )
        await message.answer(
            "📱 Пожалуйста, предоставьте ваш номер телефона.",
            reply_markup=phone_keyboard(),
        )
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
    await callback.message.answer(
        "Введите вашу дату рождения в формате ДД.ММ.ГГГГ (например, 01.01.2000):"
    )
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
            role='user',
        )
        session.add(new_user)
        await session.commit()
    await message.answer(
        f"🎉 Регистрация завершена!\n\n"
        f"ФИО: {data['full_name']}\nПол: {data['gender']}\n"
        f"Дата рождения: {b_date.strftime('%d.%m.%Y')}\n\nДобро пожаловать!",
        reply_markup=main_menu_keyboard(False),
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
        await start_feedback(message)
    elif text == "🔧 Админ-панель" and user.role == 'admin':
        await admin_panel(message)
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
        await callback.message.answer("Главное меню:", reply_markup=main_menu_keyboard(user.role == 'admin'))
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
        await callback.message.edit_text(
            "🔔 Настройки уведомлений (в разработке).",
            reply_markup=notify_settings_keyboard(),
        )
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
        await message.answer(
            "❌ Некорректный username. Используйте формат @example или example (5-32 символов, буквы, цифры, _)."
        )
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
        stmt = (
            select(Event)
            .where(Event.date_time > func.now(), Event.status == 'active', Event.is_archived == False)
            .order_by(Event.date_time)
            .limit(4)
        )
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
        reg = await session.execute(
            select(Registration).where(
                Registration.user_id == user.id,
                Registration.events_id == event_id,
                Registration.status.in_(['registered', 'waiting']),
            )
        )
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
    await callback.message.edit_text(
        text,
        reply_markup=event_card_keyboard(event.id, is_registered, can_register),
        parse_mode="Markdown",
    )
    await callback.answer()

async def register_for_event(callback: types.CallbackQuery):
    event_id = int(callback.data.split("_")[1])
    user = await get_user(callback.from_user.id)
    async with async_session() as session:
        existing = await session.execute(
            select(Registration).where(
                Registration.user_id == user.id,
                Registration.events_id == event_id,
                Registration.status.in_(['registered', 'waiting']),
            )
        )
        if existing.scalar_one_or_none():
            await callback.answer("Вы уже записаны или в очереди.", show_alert=True)
            return
        event = await session.get(Event, event_id)
        if not event or event.status != 'active':
            await callback.answer("Мероприятие неактивно.", show_alert=True)
            return
        regs = await count_registered(event.id)
        if event.participants_limit and regs >= event.participants_limit:
            max_q = await session.scalar(
                select(func.max(Registration.queue_position)).where(
                    Registration.events_id == event_id, Registration.status == 'waiting'
                )
            )
            new_pos = (max_q or 0) + 1
            session.add(
                Registration(
                    user_id=user.id,
                    events_id=event_id,
                    status='waiting',
                    queue_position=new_pos,
                )
            )
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
            select(Registration)
            .where(
                Registration.user_id == user.id,
                Registration.status.in_(['registered', 'waiting']),
            )
            .order_by(Registration.created_at.desc())
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
    await callback.message.edit_text(
        text,
        reply_markup=registration_card_keyboard(reg.id, event.id, can_cancel),
        parse_mode="Markdown",
    )
    await callback.answer()

# ================== ОТЗЫВЫ ==================
async def start_feedback(message_or_callback):
    user = await get_user(message_or_callback.from_user.id)
    async with async_session() as session:
        regs = await session.execute(
            select(Registration)
            .join(Event)
            .where(
                Registration.user_id == user.id,
                Registration.status == 'registered',
                Event.date_time < func.now(),
            )
            .order_by(Event.date_time.desc())
        )
        regs = regs.scalars().all()
        events = []
        for r in regs:
            await session.refresh(r, ['event'])
            if r.event not in events:
                events.append(r.event)
    if events:
        text = "Выберите мероприятие, о котором хотите оставить отзыв:"
        keyboard = feedback_event_keyboard(events)
    else:
        text = (
            "У вас нет посещённых мероприятий. Можете оставить отзыв о центре в целом.\n"
            "Напишите ваш отзыв сейчас или отправьте /cancel для отмены."
        )
        keyboard = None
    if isinstance(message_or_callback, types.Message):
        if keyboard:
            await message_or_callback.answer(text, reply_markup=keyboard)
        else:
            await message_or_callback.answer(text)
    else:
        if keyboard:
            await message_or_callback.message.edit_text(text, reply_markup=keyboard)
        else:
            await message_or_callback.message.edit_text(text)

async def feedback_chosen(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data
    if data == "feedback_center":
        await state.update_data(feedback_event_id=None)
        await callback.message.edit_text("Напишите ваш отзыв о Центре молодёжных инициатив:")
        await state.set_state(FeedbackFlow.waiting_for_text)
    elif data.startswith("feedback_event_"):
        event_id = int(data.split("_")[2])
        await state.update_data(feedback_event_id=event_id)
        await callback.message.edit_text("Напишите ваш отзыв о мероприятии:")
        await state.set_state(FeedbackFlow.waiting_for_text)
    await callback.answer()

async def save_feedback(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if not text:
        await message.answer("Отзыв не может быть пустым. Попробуйте ещё раз.")
        return
    data = await state.get_data()
    event_id = data.get('feedback_event_id')
    user = await get_user(message.from_user.id)
    async with async_session() as session:
        feedback = Feedback(user_id=user.id, events_id=event_id, content=text)
        session.add(feedback)
        await session.commit()
    await message.answer("✅ Спасибо за ваш отзыв!", reply_markup=main_menu_keyboard(False))
    await state.clear()

# ================== АДМИН-ПАНЕЛЬ (бот) ==================
async def admin_panel(message_or_callback):
    if isinstance(message_or_callback, types.Message):
        await message_or_callback.answer("🔧 Админ-панель", reply_markup=admin_main_keyboard())
    else:
        await message_or_callback.message.edit_text("🔧 Админ-панель", reply_markup=admin_main_keyboard())

async def admin_users_list(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])  # admin_users_<page>
    per_page = 5
    offset = (page - 1) * per_page
    async with async_session() as session:
        total = await session.scalar(select(func.count(User.id)))
        users = (
            (await session.execute(select(User).order_by(User.id).offset(offset).limit(per_page)))
            .scalars()
            .all()
        )
    total_pages = max(1, (total + per_page - 1) // per_page)
    await callback.message.edit_text(
        f"👥 Пользователи (страница {page}/{total_pages}):",
        reply_markup=admin_users_keyboard(users, page, total_pages),
    )
    await callback.answer()

async def admin_events_list(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2]) if len(callback.data.split("_")) == 3 else 1
    per_page = 4
    offset = (page - 1) * per_page
    async with async_session() as session:
        total = await session.scalar(select(func.count(Event.id)))
        events = (
            (await session.execute(select(Event).order_by(Event.date_time.desc()).offset(offset).limit(per_page)))
            .scalars()
            .all()
        )
    total_pages = max(1, (total + per_page - 1) // per_page)
    await callback.message.edit_text(
        f"📋 Мероприятия (страница {page}/{total_pages}):",
        reply_markup=admin_events_keyboard(events, page, total_pages),
    )
    await callback.answer()

async def admin_feedbacks_list(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2]) if len(callback.data.split("_")) == 3 else 1
    per_page = 5
    offset = (page - 1) * per_page
    async with async_session() as session:
        total = await session.scalar(select(func.count(Feedback.id)))
        feedbacks = (
            (await session.execute(select(Feedback).order_by(Feedback.created_at.desc()).offset(offset).limit(per_page)))
            .scalars()
            .all()
        )
    total_pages = max(1, (total + per_page - 1) // per_page)
    await callback.message.edit_text(
        f"💬 Отзывы (страница {page}/{total_pages}):",
        reply_markup=admin_feedbacks_keyboard(feedbacks, page, total_pages),
    )
    await callback.answer()

async def admin_event_create_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите название мероприятия:")
    await state.set_state(AdminEventCreate.waiting_for_title)
    await callback.answer()

async def admin_event_create_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await message.answer("Введите описание:")
    await state.set_state(AdminEventCreate.waiting_for_description)

async def admin_event_create_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await message.answer("Введите дату в формате ДД.ММ.ГГГГ:")
    await state.set_state(AdminEventCreate.waiting_for_date)

async def admin_event_create_date(message: types.Message, state: FSMContext):
    d = message.text.strip()
    if not re.match(r"^\d{2}\.\d{2}\.\d{4}$", d):
        await message.answer("Неверный формат. Введите ДД.ММ.ГГГГ:")
        return
    await state.update_data(date=d)
    await message.answer("Введите время в формате ЧЧ:ММ:")
    await state.set_state(AdminEventCreate.waiting_for_time)

async def admin_event_create_time(message: types.Message, state: FSMContext):
    t = message.text.strip()
    if not re.match(r"^\d{2}:\d{2}$", t):
        await message.answer("Введите ЧЧ:ММ:")
        return
    await state.update_data(time=t)
    await message.answer("Введите место проведения:")
    await state.set_state(AdminEventCreate.waiting_for_location)

async def admin_event_create_location(message: types.Message, state: FSMContext):
    await state.update_data(location=message.text.strip())
    await message.answer("Введите лимит участников (0 = без ограничений):")
    await state.set_state(AdminEventCreate.waiting_for_limit)

async def admin_event_create_limit(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Введите число.")
        return
    await state.update_data(limit=int(message.text))
    await message.answer("Мероприятие платное? (да/нет):")
    await state.set_state(AdminEventCreate.waiting_for_is_paid)

async def admin_event_create_is_paid(message: types.Message, state: FSMContext):
    answer = message.text.strip().lower()
    is_paid = answer in ("да", "yes", "y")
    data = await state.get_data()
    date_str = data['date']
    time_str = data['time']
    dt = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
    async with async_session() as session:
        new_event = Event(
            title=data['title'],
            description=data.get('description'),
            date_time=dt,
            location=data.get('location'),
            participants_limit=data['limit'],
            is_paid=is_paid,
        )
        session.add(new_event)
        await session.commit()
    await message.answer("✅ Мероприятие создано!", reply_markup=main_menu_keyboard(True))
    await state.clear()

async def admin_event_edit(callback: types.CallbackQuery):
    event_id = int(callback.data.split("_")[3])
    await callback.message.answer(
        "Выберите поле для редактирования:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Название", callback_data=f"editfield_title_{event_id}")],
            [InlineKeyboardButton(text="Описание", callback_data=f"editfield_desc_{event_id}")],
            [InlineKeyboardButton(text="Дату и время", callback_data=f"editfield_datetime_{event_id}")],
            [InlineKeyboardButton(text="Место", callback_data=f"editfield_location_{event_id}")],
            [InlineKeyboardButton(text="Лимит", callback_data=f"editfield_limit_{event_id}")],
            [InlineKeyboardButton(text="Статус", callback_data=f"editfield_status_{event_id}")],
            [InlineKeyboardButton(text="Отмена", callback_data="admin_events_1")],
        ]),
    )
    await callback.answer()

async def admin_event_edit_field(callback: types.CallbackQuery, state: FSMContext):
    field, event_id = callback.data.split("_")[1], int(callback.data.split("_")[2])
    await state.update_data(edit_event_id=event_id, edit_field=field)
    await callback.message.answer(f"Введите новое значение для поля '{field}':")
    await state.set_state(AdminEventEdit.waiting_for_value)
    await callback.answer()

async def admin_event_edit_value(message: types.Message, state: FSMContext):
    data = await state.get_data()
    event_id = data['edit_event_id']
    field = data['edit_field']
    value = message.text.strip()
    async with async_session() as session:
        event = await session.get(Event, event_id)
        if not event:
            await message.answer("Мероприятие не найдено.")
            return
        if field == "title":
            event.title = value
        elif field == "desc":
            event.description = value
        elif field == "datetime":
            try:
                dt = datetime.strptime(value, "%d.%m.%Y %H:%M")
                event.date_time = dt
            except Exception:
                await message.answer("Неверный формат. Используйте ДД.ММ.ГГГГ ЧЧ:ММ")
                return
        elif field == "location":
            event.location = value
        elif field == "limit":
            if value.isdigit():
                event.participants_limit = int(value)
            else:
                await message.answer("Лимит должен быть числом.")
                return
        elif field == "status":
            if value in ('active', 'cancelled', 'finished'):
                event.status = value
            else:
                await message.answer("Допустимые статусы: active, cancelled, finished")
                return
        await session.commit()
    await message.answer("✅ Поле обновлено.")
    await state.clear()

async def admin_event_delete(callback: types.CallbackQuery):
    event_id = int(callback.data.split("_")[3])
    async with async_session() as session:
        event = await session.get(Event, event_id)
        if event:
            event.is_archived = True  # мягкое удаление
            await session.commit()
    await callback.message.answer("Мероприятие помечено как удалённое.")
    await admin_events_list(callback)

async def admin_feedback_detail(callback: types.CallbackQuery):
    fb_id = int(callback.data.split("_")[2])
    async with async_session() as session:
        fb = await session.get(Feedback, fb_id)
        if not fb:
            await callback.answer("Отзыв не найден.")
            return
        user = await session.get(User, fb.user_id)
        event = await session.get(Event, fb.events_id) if fb.events_id else None
        text = f"💬 Отзыв #{fb.id}\nОт: {user.full_name} ({user.telegram_id})\n"
        if event:
            text += f"О мероприятии: {event.title}\n"
        else:
            text += "О центре в целом\n"
        text += f"Текст: {fb.content}\nДата: {fb.created_at.strftime('%d.%m.%Y %H:%M')}"
    await callback.message.answer(text)
    await callback.answer()

async def admin_broadcast_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите текст сообщения для рассылки всем пользователям:")
    await state.set_state(AdminBroadcast.waiting_for_message)
    await callback.answer()

async def admin_broadcast_message(message: types.Message, state: FSMContext):
    await state.update_data(broadcast_text=message.text.strip())
    await message.answer(
        f"Отправить это сообщение всем пользователям?\n\n{message.text.strip()}\n\nПодтвердите: да/нет",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, отправить", callback_data="broadcast_confirm")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")],
        ]),
    )
    await state.set_state(AdminBroadcast.confirm)

async def admin_broadcast_confirm(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = data['broadcast_text']
    async with async_session() as session:
        users = (await session.execute(select(User.telegram_id))).scalars().all()
    sent = 0
    for uid in users:
        try:
            await callback.bot.send_message(uid, text)
            sent += 1
        except Exception:
            pass
    await callback.message.answer(f"Рассылка завершена. Отправлено {sent} из {len(users)}.")
    await state.clear()
    await callback.answer()

async def admin_broadcast_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("Рассылка отменена.")
    await callback.answer()

# ================== Команда /seed ==================
async def cmd_seed(message: types.Message):
    user = await get_user(message.from_user.id)
    if not user or user.role != 'admin':
        await message.answer("⛔ Недостаточно прав.")
        return
    test_events = [
        {
            "title": "Квиз «Молодежь и наука»",
            "description": "Интеллектуальная игра для студентов.",
            "date_time": datetime(2026, 6, 15, 18, 0),
            "location": "ул. Ленина, 10",
            "participants_limit": 20,
            "is_paid": False,
        },
        {
            "title": "Мастер-класс по SMM",
            "description": "Практический семинар.",
            "date_time": datetime(2026, 7, 1, 15, 0),
            "location": "Центр молодежных инициатив",
            "participants_limit": 15,
            "is_paid": True,
        },
        {
            "title": "Велопробег «Вперед!»",
            "description": "Спортивный заезд.",
            "date_time": datetime(2026, 8, 20, 10, 0),
            "location": "Старт от площади Ленина",
            "participants_limit": 0,
            "is_paid": False,
        },
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
        is_admin = user.role == 'admin'
        await message.answer("Главное меню:", reply_markup=main_menu_keyboard(is_admin))
    else:
        await message.answer("Сначала /start")

# ---------- Эхо ----------
async def echo(message: types.Message):
    await message.answer("Используйте /start или кнопки меню.")
