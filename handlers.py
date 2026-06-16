from aiogram import Bot, types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart, StateFilter, Command
from sqlalchemy import select, func, delete, update
from datetime import datetime, date

from config import async_session
from models import User, Event, Registration, Feedback, NotifySetting
from states import Registration as RegState, ProfileEdit, FeedbackFlow
from keyboards import (
    phone_keyboard, gender_keyboard, remove_keyboard,
    main_menu_keyboard, profile_menu_keyboard, notify_settings_keyboard,
    events_list_keyboard, event_card_keyboard,
    my_registrations_keyboard, registration_card_keyboard,
    feedback_event_keyboard, skip_keyboard, cancel_feedback_keyboard
)
from validators import (
    is_valid_full_name, contains_emoji, is_valid_birthday,
    is_valid_vk_url, is_valid_tg_username, is_valid_email,
    is_valid_phone
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
            select(Registration)
            .where(Registration.events_id == event_id, Registration.status == 'waiting')
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
                await bot.send_message(user.telegram_id, "🎉 Освободилось место! Вы автоматически записаны.")
            except Exception:
                pass
        remaining = await session.execute(
            select(Registration)
            .where(Registration.events_id == event_id, Registration.status == 'waiting')
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
    user = await get_user(message.chat.id)
    if user:
        await message.answer(
            f"С возвращением, {user.full_name}!\nЧто хотите сделать?",
            reply_markup=main_menu_keyboard()
        )
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
    if not is_valid_phone(phone):
        await message.answer("❌ Введите номер в формате +7XXXXXXXXXX (10 цифр после +7).")
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
        notify_setting = NotifySetting(
            user_id=new_user.id,
            notification_type='event_reminder',
            is_enabled=True
        )
        session.add(notify_setting)
        await session.commit()
    # Переход к сбору tg_username вместо завершения
    await message.answer(
        "📱 Введите ваш Telegram username (например, @example) или нажмите «Пропустить»:",
        reply_markup=skip_keyboard()
    )
    await state.set_state(RegState.waiting_for_tg_username)

# --- Новые шаги регистрации: tg_username, vk, email ---
async def process_tg_username(message: types.Message, state: FSMContext):
    username = message.text.strip()
    if not is_valid_tg_username(username):
        await message.answer("❌ Некорректный username. Попробуйте ещё раз или нажмите «Пропустить».")
        return
    if username.startswith('@'):
        username = username[1:]
    user = await get_user(message.from_user.id)
    async with async_session() as session:
        user = await session.merge(user)
        user.tg_username = username
        await session.commit()
    await message.answer("🔗 Введите вашу ссылку на VK (например, https://vk.com/id123) или нажмите «Пропустить»:", reply_markup=skip_keyboard())
    await state.set_state(RegState.waiting_for_vk)

async def skip_tg_username(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🔗 Введите вашу ссылку на VK (например, https://vk.com/id123) или нажмите «Пропустить»:", reply_markup=skip_keyboard())
    await state.set_state(RegState.waiting_for_vk)
    await callback.answer()

async def process_vk(message: types.Message, state: FSMContext):
    vk_url = message.text.strip()
    if not is_valid_vk_url(vk_url):
        await message.answer("❌ Некорректная ссылка VK. Попробуйте ещё раз или нажмите «Пропустить».")
        return
    user = await get_user(message.from_user.id)
    async with async_session() as session:
        user = await session.merge(user)
        user.vk_url = vk_url
        await session.commit()
    await message.answer("✉️ Введите ваш email (например, example@mail.ru) или нажмите «Пропустить»:", reply_markup=skip_keyboard())
    await state.set_state(RegState.waiting_for_email)

async def skip_vk(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("✉️ Введите ваш email (например, example@mail.ru) или нажмите «Пропустить»:", reply_markup=skip_keyboard())
    await state.set_state(RegState.waiting_for_email)
    await callback.answer()

async def process_email(message: types.Message, state: FSMContext):
    email = message.text.strip()
    if not is_valid_email(email):
        await message.answer("❌ Некорректный email. Попробуйте ещё раз или нажмите «Пропустить».")
        return
    user = await get_user(message.from_user.id)
    async with async_session() as session:
        user = await session.merge(user)
        user.email = email
        await session.commit()
    await finish_registration(message, state)

async def skip_email(callback: types.CallbackQuery, state: FSMContext):
    await finish_registration(callback.message, state)
    await callback.answer()

async def finish_registration(message: types.Message, state: FSMContext, is_callback=False):
    user = await get_user(message.chat.id)
    # Финальное сообщение с заполненным профилем
    await message.answer(
        f"🎉 Регистрация завершена!\n\n"
        f"ФИО: {user.full_name}\nПол: {user.gender}\n"
        f"Дата рождения: {user.birthday.strftime('%d.%m.%Y') if user.birthday else 'не указана'}\n"
        f"Telegram: @{user.tg_username if user.tg_username else 'не указан'}\n"
        f"VK: {user.vk_url or 'не указана'}\n"
        f"Email: {user.email or 'не указан'}\n\nДобро пожаловать!",
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
        await start_feedback(message, state)
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
        async with async_session() as session:
            setting = await session.execute(
                select(NotifySetting).where(
                    NotifySetting.user_id == user.id,
                    NotifySetting.notification_type == 'event_reminder'
                )
            )
            setting = setting.scalar_one_or_none()
            is_enabled = setting.is_enabled if setting else True
        await callback.message.edit_text(
            "🔔 Настройки уведомлений",
            reply_markup=notify_settings_keyboard(enabled=is_enabled)
        )
    elif action == "toggle_notify":
        async with async_session() as session:
            setting = await session.execute(
                select(NotifySetting).where(
                    NotifySetting.user_id == user.id,
                    NotifySetting.notification_type == 'event_reminder'
                )
            )
            setting = setting.scalar_one_or_none()
            if setting:
                setting.is_enabled = not setting.is_enabled
            else:
                # Если записи не было, создаём с выключенным состоянием (пользователь нажал "выключить")
                setting = NotifySetting(user_id=user.id, notification_type='event_reminder', is_enabled=False)
                session.add(setting)
            await session.commit()
            new_status = setting.is_enabled
        await callback.message.edit_text(
            "🔔 Настройки уведомлений",
            reply_markup=notify_settings_keyboard(enabled=new_status)
        )
        await callback.answer(f"Уведомления {'включены' if new_status else 'выключены'}")
    elif action == "delete_account":
        await delete_account_confirm(callback)
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
    if not is_valid_phone(phone):
        await message.answer("❌ Введите номер в формате +7XXXXXXXXXX (10 цифр после +7).")
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
        stmt = select(Event).where(
            Event.date_time > func.now(), Event.status == 'active', Event.is_archived == False
        ).order_by(Event.date_time).limit(4)
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
                Registration.status.in_(['registered', 'waiting'])
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
        text, reply_markup=event_card_keyboard(event.id, is_registered, can_register), parse_mode="Markdown"
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
                Registration.status.in_(['registered', 'waiting'])
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
            select(Registration)
            .where(Registration.user_id == user.id, Registration.status.in_(['registered', 'waiting']))
            .order_by(Registration.created_at.desc())
        )
        regs = regs.scalars().all()

        # Загружаем все связанные события одним запросом
        event_ids = [r.events_id for r in regs]
        if event_ids:
            events = (await session.execute(
                select(Event).where(Event.id.in_(event_ids))
            )).scalars().all()
            event_map = {e.id: e for e in events}
            for r in regs:
                r.event = event_map.get(r.events_id)   # "прикрепляем" событие к регистрации
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
        event = await session.get(Event, reg.events_id)
        if not event:
            await callback.answer("Мероприятие не найдено.")
            return
        can_cancel = reg.status in ('registered', 'waiting') and event.date_time > datetime.now()
    text = (
        f"**{event.title}**\n📅 {event.date_time.strftime('%d.%m.%Y в %H:%M')}\n"
        f"📍 {event.location or 'Не указано'}\n"
        f"Статус: {'✅ Записан' if reg.status == 'registered' else '🕒 В очереди'}\n"
    )
    if reg.status == 'waiting':
        text += f"Позиция в очереди: {reg.queue_position}\n"
    await callback.message.edit_text(
        text, reply_markup=registration_card_keyboard(reg.id, event.id, can_cancel), parse_mode="Markdown"
    )
    await callback.answer()

# ================== ОТЗЫВЫ ==================
async def start_feedback(message_or_callback, state: FSMContext = None):
    user = await get_user(message_or_callback.from_user.id)
    async with async_session() as session:
        regs = await session.execute(
            select(Registration).join(Event)
            .where(Registration.user_id == user.id, Registration.status == 'registered', Event.date_time < func.now())
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
        text = "У вас нет посещённых мероприятий. Можете оставить отзыв о центре в целом.\nНапишите ваш отзыв сейчас."
        keyboard = cancel_feedback_keyboard()   # всегда показываем отмену

    if isinstance(message_or_callback, types.Message):
        if keyboard:
            await message_or_callback.answer(text, reply_markup=keyboard)
        else:
            await message_or_callback.answer(text)
            if state:
                await state.set_state(FeedbackFlow.waiting_for_text)
    else:
        if keyboard:
            await message_or_callback.message.edit_text(text, reply_markup=keyboard)
        else:
            await message_or_callback.message.edit_text(text)

async def cancel_feedback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_user(callback.from_user.id)
    if user:
        await callback.message.answer("Главное меню:", reply_markup=main_menu_keyboard())
    else:
        await callback.message.answer("Сначала /start")
    await callback.answer()

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
    async with async_session() as session:
        admins = await session.execute(select(User).where(User.role == 'admin'))
        admins = admins.scalars().all()

    for admin in admins:
        try:
            await message.bot.send_message(
                admin.telegram_id,
                f"📝 Новый отзыв от {user.full_name} (ID {user.telegram_id}):\n{text}"
            )
        except Exception:
            pass
    await message.answer("✅ Спасибо за ваш отзыв!", reply_markup=main_menu_keyboard())
    await state.clear()

# ---------- Удаление аккаунта ----------
async def delete_account_confirm(callback: types.CallbackQuery):
    """Запрашивает подтверждение удаления аккаунта."""
    await callback.message.answer(
        "⚠️ Вы уверены, что хотите удалить аккаунт?\n"
        "Все ваши данные (профиль, записи на мероприятия, отзывы) будут безвозвратно удалены.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data="delete_account_execute")],
            [InlineKeyboardButton(text="❌ Нет, оставить", callback_data="profile_menu")]
        ])
    )
    await callback.answer()

async def delete_account_execute(callback: types.CallbackQuery, bot: Bot):
    """Выполняет удаление аккаунта и всех связанных данных."""
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден.")
        return

    # Отменяем все активные регистрации (чтобы освободить места и продвинуть очередь)
    async with async_session() as session:
        active_regs = await session.execute(
            select(Registration).where(
                Registration.user_id == user.id,
                Registration.status.in_(['registered', 'waiting'])
            )
        )
        active_regs = active_regs.scalars().all()
        for reg in active_regs:
            await cancel_registration(reg.events_id, user.id, bot)

    # Удаляем все данные пользователя
    async with async_session() as session:
        await session.execute(delete(Registration).where(Registration.user_id == user.id))
        await session.execute(delete(Feedback).where(Feedback.user_id == user.id))
        await session.execute(delete(NotifySetting).where(NotifySetting.user_id == user.id))
        # Если есть таблица auth_codes, тоже удаляем (на ваше усмотрение)
        # await session.execute(delete(AuthCode).where(AuthCode.user_id == user.id))
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()

    await callback.message.answer(
        "👋 Ваш аккаунт полностью удалён. Если захотите вернуться, просто введите /start.",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer("Аккаунт удалён")
    
# ---------- /menu ----------
async def cmd_menu(message: types.Message):
    user = await get_user(message.from_user.id)
    if user:
        await message.answer("Главное меню:", reply_markup=main_menu_keyboard())
    else:
        await message.answer("Сначала /start")

# ---------- Команда /cancel ----------
async def cmd_cancel(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
        user = await get_user(message.from_user.id)
        if user:
            await message.answer("🚫 Действие отменено.", reply_markup=main_menu_keyboard())
        else:
            await message.answer("🚫 Действие отменено. Введите /start для начала.")
    else:
        await message.answer("🤷 Нет активного действия для отмены.")

# ---------- Эхо ----------
async def echo(message: types.Message):
    await message.answer("Используйте /start или кнопки меню.")
