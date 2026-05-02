from aiogram.fsm.state import StatesGroup, State

class Registration(StatesGroup):
    waiting_for_phone = State()
    waiting_for_full_name = State()
    waiting_for_gender = State()
    waiting_for_birthday = State()

class ProfileEdit(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_phone = State()
    waiting_for_gender = State()
    waiting_for_birthday = State()
    waiting_for_vk = State()
    waiting_for_tg_username = State()    # <-- новое
    waiting_for_email = State()          # <-- новое
