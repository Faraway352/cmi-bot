from aiogram.fsm.state import StatesGroup, State

class Registration(StatesGroup):
    waiting_for_phone = State()
    waiting_for_first_name = State()
    waiting_for_last_name = State()
    waiting_for_gender = State()
    waiting_for_birth_date = State()   # вместо waiting_for_age
