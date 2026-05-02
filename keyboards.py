from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove
)

def phone_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Предоставить номер", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )

def gender_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мужской", callback_data="gender_male"),
         InlineKeyboardButton(text="Женский", callback_data="gender_female")]
    ])

def remove_keyboard():
    return ReplyKeyboardRemove()

# ---------- Главное меню ----------
def main_menu_keyboard(is_admin: bool = False):
    keyboard = [
        [KeyboardButton(text="🎉 Афиша")],
        [KeyboardButton(text="📋 Мои записи")],
        [KeyboardButton(text="👤 Личный кабинет")],
        [KeyboardButton(text="💬 Оставить отзыв")]
    ]
    if is_admin:
        keyboard.append([KeyboardButton(text="🔧 Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

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

def notify_settings_keyboard(enabled: bool = True):
    status = "✅ Включены" if enabled else "❌ Отключены"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=status, callback_data="toggle_notify")],
        [InlineKeyboardButton(text="🔙 Назад в профиль", callback_data="profile_menu")]
    ])

# ---------- Афиша ----------
def events_list_keyboard(events: list):
    buttons = []
    for ev in events:
        short = (ev.title[:30] + "…") if len(ev.title) > 30 else ev.title
        buttons.append([InlineKeyboardButton(
            text=f"{short} ({ev.date_time.strftime('%d.%m %H:%M')})",
            callback_data=f"event_{ev.id}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 В главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def event_card_keyboard(event_id: int, is_registered: bool, can_register: bool):
    buttons = []
    if is_registered:
        buttons.append([InlineKeyboardButton(text="❌ Отменить запись", callback_data=f"cancel_reg_{event_id}")])
    elif can_register:
        buttons.append([InlineKeyboardButton(text="✅ Записаться", callback_data=f"register_{event_id}")])
    else:
        buttons.append([InlineKeyboardButton(text="🕒 Встать в очередь", callback_data=f"enqueue_{event_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 К афише", callback_data="show_events")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ---------- Мои записи ----------
def my_registrations_keyboard(registrations: list):
    buttons = []
    for reg in registrations:
        ev = reg.event
        short = (ev.title[:30] + "…") if len(ev.title) > 30 else ev.title
        icon = {"registered": "✅", "waiting": "🕒", "cancelled": "❌"}.get(reg.status, "")
        buttons.append([InlineKeyboardButton(
            text=f"{icon} {short} ({ev.date_time.strftime('%d.%m %H:%M')})",
            callback_data=f"myreg_{reg.id}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 В главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def registration_card_keyboard(reg_id: int, event_id: int, can_cancel: bool):
    buttons = []
    if can_cancel:
        buttons.append([InlineKeyboardButton(text="❌ Отменить запись", callback_data=f"cancel_reg_{event_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 К моим записям", callback_data="my_registrations")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ---------- Отзывы ----------
def feedback_event_keyboard(events: list):
    buttons = []
    for ev in events:
        short = (ev.title[:30] + "…") if len(ev.title) > 30 else ev.title
        buttons.append([InlineKeyboardButton(
            text=f"📝 {short} ({ev.date_time.strftime('%d.%m.%Y')})",
            callback_data=f"feedback_event_{ev.id}"
        )])
    buttons.append([InlineKeyboardButton(text="🏢 О центре в целом", callback_data="feedback_center")])
    buttons.append([InlineKeyboardButton(text="🔙 В главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ---------- Админ-панель ----------
def admin_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users_1")],
        [InlineKeyboardButton(text="📋 Мероприятия", callback_data="admin_events_1")],
        [InlineKeyboardButton(text="💬 Отзывы", callback_data="admin_feedbacks_1")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="main_menu")]
    ])

def admin_users_keyboard(users: list, page: int, total_pages: int):
    buttons = []
    for u in users:
        short_name = u.full_name[:25] + "…" if len(u.full_name) > 25 else u.full_name
        buttons.append([InlineKeyboardButton(
            text=f"{short_name} ({u.telegram_id})",
            callback_data=f"admin_user_{u.id}"
        )])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_users_{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="▶️ Вперёд", callback_data=f"admin_users_{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="🔙 Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_events_keyboard(events: list, page: int, total_pages: int):
    buttons = []
    for ev in events:
        short = (ev.title[:30] + "…") if len(ev.title) > 30 else ev.title
        buttons.append([InlineKeyboardButton(
            text=f"{short} ({ev.date_time.strftime('%d.%m')})",
            callback_data=f"admin_event_{ev.id}"
        )])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_events_{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="▶️ Вперёд", callback_data=f"admin_events_{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="➕ Создать мероприятие", callback_data="admin_event_create")])
    buttons.append([InlineKeyboardButton(text="🔙 Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_event_manage_keyboard(event_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"admin_event_edit_{event_id}")],
        [InlineKeyboardButton(text="❌ Удалить", callback_data=f"admin_event_delete_{event_id}")],
        [InlineKeyboardButton(text="🔙 К списку мероприятий", callback_data="admin_events_1")]
    ])

def admin_feedbacks_keyboard(feedbacks: list, page: int, total_pages: int):
    buttons = []
    for fb in feedbacks:
        preview = fb.content[:30] + "…" if len(fb.content) > 30 else fb.content
        buttons.append([InlineKeyboardButton(
            text=f"Отзыв #{fb.id}: {preview}",
            callback_data=f"admin_fb_{fb.id}"
        )])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_feedbacks_{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="▶️ Вперёд", callback_data=f"admin_feedbacks_{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="🔙 Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
