from aiogram import types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart, StateFilter
from sqlalchemy import select
from datetime import date
import re

from config import async_session
from models import User
from states import Registration, ProfileEdit
from keyboards import (
    phone_keyboard, gender_keyboard, remove_keyboard,
    main_menu_keyboard, profile_menu_keyboard, notify_settings_keyboard
)
from validators import is_valid_full_name, contains_emoji, is_valid_birthday

# ---------- Валидация VK ссылки ----------
def is_valid_vk_url(url: str) -> bool:
    """Простая проверка: строка содержит vk.com/ или https://vk.com/..."""
    if not url:
        return False
    return bool(re.match(r"^(https?://)?vk\.com/[\w.]+$", url.strip()))

# ---------- Вспомогательная функция ----------
async def get_user(telegram_id: int):
    async with async_session() as session:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

# ---------- /start ----------
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user = await get_user(message.from_user.id)
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
        await state.set_state(Registration.waiting_for_phone)

# ---------- Регистрация ----------
async def process_phone_contact(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number
    await state.update_data(phone=phone)
    await message.answer("✅ Номер получен. Введите ваше ФИО (полностью).", reply_markup=remove_keyboard())
    await state.set_state(Registration.waiting_for_full_name)

async def process_phone_manually(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    if not phone.startswith("+") or not phone[1:].isdigit():
        await message.answer("❌ Введите номер в формате +7XXXXXXXXXX или нажмите кнопку ниже.")
        return
    await state.update_data(phone=phone)
    await message.answer("Теперь введите ваше ФИО (полностью).", reply_markup=remove_keyboard())
    await state.set_state(Registration.waiting_for_full_name)

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
    await state.set_state(Registration.waiting_for_gender)

async def process_gender(callback: types.CallbackQuery, state: FSMContext):
    gender = 'Муж' if callback.data == 'gender_male' else 'Жен'
    await state.update_data(gender=gender)
    await callback.message.edit_reply_markup()
    await callback.message.answer("Введите вашу дату рождения в формате ДД.ММ.ГГГГ (например, 01.01.2000):")
    await state.set_state(Registration.waiting_for_birthday)
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
        f"ФИО: {data['full_name']}\n"
        f"Пол: {data['gender']}\n"
        f"Дата рождения: {b_date.strftime('%d.%m.%Y')}\n\n"
        f"Добро пожаловать!",
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
        await message.answer("📋 Здесь будут ваши записи на мероприятия. Раздел в разработке.")
    elif text == "🎉 Афиша":
        await message.answer("🎉 Здесь будет афиша мероприятий. Раздел в разработке.")
    elif text == "💬 Оставить отзыв":
        await message.answer("💬 Здесь можно будет оставить отзыв. Раздел в разработке.")
    else:
        await message.answer("Используйте кнопки меню.")

# ---------- Просмотр профиля ----------
async def show_profile(message_or_callback, user):
    vk = user.vk_url if user.vk_url else "не указана"
    text = (
        f"👤 **Личный кабинет**\n\n"
        f"📛 Имя: {user.full_name}\n"
        f"📞 Телефон: {user.phone}\n"
        f"⚤ Пол: {user.gender}\n"
        f"🎂 Дата рождения: {user.birthday.strftime('%d.%m.%Y') if user.birthday else 'не указана'}\n"
        f"🔗 VK: {vk}\n"
    )
    if isinstance(message_or_callback, types.Message):
        await message_or_callback.answer(text, reply_markup=profile_menu_keyboard(), parse_mode="Markdown")
    else:
        await message_or_callback.message.edit_text(text, reply_markup=profile_menu_keyboard(), parse_mode="Markdown")

# ---------- Возврат в главное меню ----------
async def process_callback_main_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_user(callback.from_user.id)
    if user:
        await callback.message.answer("Главное меню:", reply_markup=main_menu_keyboard())
    else:
        await callback.message.answer("Сначала /start")
    await callback.answer()

# ---------- Обработка inline-кнопок профиля ----------
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
        await callback.answer()
    elif action == "edit_phone":
        await callback.message.answer("Введите новый номер телефона в формате +7XXXXXXXXXX:")
        await state.set_state(ProfileEdit.waiting_for_phone)
        await callback.answer()
    elif action == "edit_gender":
        await callback.message.answer("Выберите пол:", reply_markup=gender_keyboard())
        await state.set_state(ProfileEdit.waiting_for_gender)
        await callback.answer()
    elif action == "edit_birthday":
        await callback.message.answer("Введите новую дату рождения в формате ДД.ММ.ГГГГ:")
        await state.set_state(ProfileEdit.waiting_for_birthday)
        await callback.answer()
    elif action == "edit_vk":                                           # <- новый обработчик
        await callback.message.answer("Введите ссылку на ваш профиль VK (например, https://vk.com/id123456789):")
        await state.set_state(ProfileEdit.waiting_for_vk)
        await callback.answer()
    elif action == "notify_settings":
        await callback.message.edit_text(
            "🔔 Настройки уведомлений (в разработке).",
            reply_markup=notify_settings_keyboard()
        )
        await callback.answer()
    elif action == "toggle_notify":
        await callback.answer("Раздел в разработке", show_alert=True)
    elif action == "profile_menu":
        await show_profile(callback, user)
        await callback.answer()
    else:
        await callback.answer("Неизвестное действие")

# ---------- Редактирование отдельных полей ----------
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

# ---------- Редактирование VK ----------
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

# ---------- /menu ----------
async def cmd_menu(message: types.Message):
    user = await get_user(message.from_user.id)
    if user:
        await message.answer("Главное меню:", reply_markup=main_menu_keyboard())
    else:
        await message.answer("Сначала /start")

# ---------- echo ----------
async def echo(message: types.Message):
    await message.answer("Используйте /start или кнопки меню.")
