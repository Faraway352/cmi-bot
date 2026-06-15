from aiogram.fsm.state import StatesGroup, State

class Registration(StatesGroup):
    waiting_for_phone = State()
    waiting_for_full_name = State()
    waiting_for_gender = State()
    waiting_for_birthday = State()
    waiting_for_tg_username = State()
    waiting_for_vk = State()
    waiting_for_email = State()

class ProfileEdit(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_phone = State()
    waiting_for_gender = State()
    waiting_for_birthday = State()
    waiting_for_vk = State()
    waiting_for_tg_username = State()
    waiting_for_email = State()

class FeedbackFlow(StatesGroup):
    waiting_for_text = State()

# ---------- Админка ----------
class AdminEventCreate(StatesGroup):
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_location = State()
    waiting_for_limit = State()
    waiting_for_is_paid = State()

class AdminEventEdit(StatesGroup):
    choose_field = State()
    waiting_for_value = State()

class AdminBroadcast(StatesGroup):
    waiting_for_message = State()
    confirm = State()
