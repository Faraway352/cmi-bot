from aiogram.fsm.state import StatesGroup, State

class Registration(StatesGroup):
    waiting_for_phone = State()
    waiting_for_full_name = State()      # вместо имени и фамилии – одно поле
    waiting_for_gender = State()
    waiting_for_birthday = State()       # переименовано
