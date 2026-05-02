from aiogram import types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart, StateFilter
from sqlalchemy import select
from datetime import date

from config import async_session
from models import User
from states import Registration
from keyboards import phone_keyboard, gender_keyboard, remove_keyboard
from validators import is_valid_full_name, contains_emoji, is_valid_birthday

async def cmd_start(message: types.Message, state: FSMContext):
    async with async_session() as session:
        stmt = select(User).where(User.telegram_id == message.from_user.id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            await message.answer(
                f"С возвращением, {user.full_name}!\n"
                "Вы уже зарегистрированы.\n"
                "Главное меню станет доступно позже."
            )
            return

    await message.answer(
        "Добро пожаловать! 👋 Я здесь, чтобы вам помочь.\n\n"
        "Я бот, который поможет вам с любой информацией о нашем центре.\n\n"
        "Хотите узнать о мероприятиях или записаться на них?\n\n"
        "Давайте начнем!",
        reply_markup=remove_keyboard()
    )
    await message.answer("📱 Пожалуйста, предоставьте ваш номер телефона.", reply_markup=phone_keyboard())
    await state.set_state(Registration.waiting_for_phone)

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
        f"Добро пожаловать! Скоро здесь появится главное меню."
    )
    await state.clear()

async def echo(message: types.Message):
    await message.answer("Введите /start, чтобы начать работу с ботом.")
