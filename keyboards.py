from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove
)

# ---------- Регистрация ----------
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

# ---------- Главное меню (обычные кнопки) ----------
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

# ---------- Профиль ----------
def profile_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить имя", callback_data="edit_full_name")],
        [InlineKeyboardButton(text="📞 Изменить телефон", callback_data="edit_phone")],
        [InlineKeyboardButton(text="⚤ Изменить пол", callback_data="edit_gender")],
        [InlineKeyboardButton(text="🎂 Изменить дату рождения", callback_data="edit_birthday")],
        [InlineKeyboardButton(text="🔗 Изменить VK", callback_data="edit_vk")],
        [InlineKeyboardButton(text="💬 Изменить Telegram", callback_data="edit_tg_username")],
        [InlineKeyboardButton(text="✉️ Изменить Email", callback_data="edit_email")],
        [InlineKeyboardButton(text="🔔 Уведомления", callback_data="notify_settings")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
    ])

def notify_settings_keyboard(notifications_enabled: bool = True):
    status = "✅ Включены" if notifications_enabled else "❌ Отключены"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=status, callback_data="toggle_notify")],
        [InlineKeyboardButton(text="🔙 Назад в профиль", callback_data="profile_menu")]
    ])

# ---------- Афиша ----------
def events_list_keyboard(events: list):
    """Создаёт клавиатуру из списка мероприятий (не более 4)"""
    buttons = []
    for ev in events:
        # Обрезаем название до 30 символов для кнопки
        short_title = ev.title[:30] + "…" if len(ev.title) > 30 else ev.title
        buttons.append([InlineKeyboardButton(
            text=f"{short_title} ({ev.date_time.strftime('%d.%m %H:%M')})",
            callback_data=f"event_{ev.id}"
        )])
    # Кнопка "Назад" в главное меню (по callback главного меню)
    buttons.append([InlineKeyboardButton(text="🔙 В главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def event_card_keyboard(event_id: int, is_registered: bool = False, can_register: bool = True):
    """Клавиатура для карточки мероприятия"""
    buttons = []
    if is_registered:
        buttons.append([InlineKeyboardButton(text="❌ Отменить запись", callback_data=f"cancel_reg_{event_id}")])
    elif can_register:
        buttons.append([InlineKeyboardButton(text="✅ Записаться", callback_data=f"register_{event_id}")])
    else:
        # Если места кончились – кнопка "В очередь"
        buttons.append([InlineKeyboardButton(text="🕒 Встать в очередь", callback_data=f"enqueue_{event_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 К афише", callback_data="show_events")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ---------- Мои записи ----------
def my_registrations_keyboard(registrations: list):
    """Кнопки для списка записей пользователя"""
    buttons = []
    for reg in registrations:
        event = reg.event  # предполагается загрузка связанного объекта
        short_title = event.title[:30] + "…" if len(event.title) > 30 else event.title
        status_icon = {"registered": "✅", "waiting": "🕒", "cancelled": "❌"}.get(reg.status, "")
        buttons.append([InlineKeyboardButton(
            text=f"{status_icon} {short_title} ({event.date_time.strftime('%d.%m %H:%M')})",
            callback_data=f"myreg_{reg.id}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 В главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def registration_card_keyboard(reg_id: int, event_id: int, can_cancel: bool = True):
    """Клавиатура внутри карточки записи"""
    buttons = []
    if can_cancel:
        buttons.append([InlineKeyboardButton(text="❌ Отменить запись", callback_data=f"cancel_reg_{event_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 К моим записям", callback_data="my_registrations")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
