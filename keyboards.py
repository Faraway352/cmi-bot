from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove
)

def phone_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Предоставить номер", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def gender_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мужской", callback_data="gender_male"),
         InlineKeyboardButton(text="Женский", callback_data="gender_female")]
    ])

def remove_keyboard():
    return ReplyKeyboardRemove()

def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎉 Афиша")],
            [KeyboardButton(text="📋 Мои записи")],
            [KeyboardButton(text="👤 Личный кабинет")],
            [KeyboardButton(text="💬 Оставить отзыв")]
        ],
        resize_keyboard=True
    )

def profile_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить имя", callback_data="edit_full_name")],
        [InlineKeyboardButton(text="📞 Изменить телефон", callback_data="edit_phone")],
        [InlineKeyboardButton(text="⚤ Изменить пол", callback_data="edit_gender")],
        [InlineKeyboardButton(text="🎂 Изменить дату рождения", callback_data="edit_birthday")],
        [InlineKeyboardButton(text="🔗 Изменить VK", callback_data="edit_vk")],
        [InlineKeyboardButton(text="💬 Изменить Telegram", callback_data="edit_tg_username")],   # <-- новое
        [InlineKeyboardButton(text="✉️ Изменить Email", callback_data="edit_email")],           # <-- новое
        [InlineKeyboardButton(text="🔔 Уведомления", callback_data="notify_settings")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
    ])

def notify_settings_keyboard(notifications_enabled: bool = True):
    status = "✅ Включены" if notifications_enabled else "❌ Отключены"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=status, callback_data="toggle_notify")],
        [InlineKeyboardButton(text="🔙 Назад в профиль", callback_data="profile_menu")]
    ])
