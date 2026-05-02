from aiogram.fsm.state import StatesGroup, State

class Registration(StatesGroup):
    waiting_for_phone = State()
    waiting_for_full_name = State()
    waiting_for_gender = State()
    waiting_for_birthday = State()

# Состояния для личного кабинета (редактирование отдельных полей)
class ProfileEdit(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_phone = State()
    waiting_for_gender = State()
    waiting_for_birthday = State()
