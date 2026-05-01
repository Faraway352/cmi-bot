import re
from datetime import date

def is_valid_name(text: str) -> bool:
    """Только буквы (кириллица/латиница), пробел и дефис, не менее 1 символа"""
    if not text:
        return False
    pattern = r"^[A-Za-zА-Яа-яёЁ\- ]+$"
    if not re.match(pattern, text):
        return False
    if len(text.strip()) < 1:
        return False
    return True

def contains_emoji(text: str) -> bool:
    """Простая проверка на наличие эмодзи"""
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # смайлики
        "\U0001F300-\U0001F5FF"  # символы и пиктограммы
        "\U0001F680-\U0001F6FF"  # транспорт и карты
        "\U0001F1E0-\U0001F1FF"  # флаги (iOS)
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE
    )
    return bool(emoji_pattern.search(text))

def is_valid_birth_date(text: str) -> bool:
    """
    Проверяет, что введена дата в формате ДД.ММ.ГГГГ,
    дата реальна, не из будущего и возраст 14–120 лет.
    """
    if contains_emoji(text):
        return False
    # Проверка формата
    if not re.match(r"^\d{2}\.\d{2}\.\d{4}$", text):
        return False
    try:
        day, month, year = map(int, text.split("."))
        b_date = date(year, month, day)
    except ValueError:
        return False  # несуществующая дата
    # Не будущее
    if b_date > date.today():
        return False
    # Проверка возраста (14–120 лет на сегодня)
    today = date.today()
    age = today.year - b_date.year - ((today.month, today.day) < (b_date.month, b_date.day))
    if not (14 <= age <= 120):
        return False
    return True
