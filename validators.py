import re
from datetime import date

def is_valid_full_name(text: str) -> bool:
    if not text:
        return False
    if not re.match(r"^[A-Za-zА-Яа-яёЁ\- ]+$", text):
        return False
    parts = text.strip().split()
    return len(parts) >= 2

def contains_emoji(text: str) -> bool:
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE
    )
    return bool(emoji_pattern.search(text))

def is_valid_birthday(text: str) -> bool:
    if contains_emoji(text):
        return False
    if not re.match(r"^\d{2}\.\d{2}\.\d{4}$", text):
        return False
    try:
        day, month, year = map(int, text.split("."))
        b_date = date(year, month, day)
    except ValueError:
        return False
    if b_date > date.today():
        return False
    today = date.today()
    age = today.year - b_date.year - ((today.month, today.day) < (b_date.month, b_date.day))
    return 14 <= age <= 120

def is_valid_vk_url(url: str) -> bool:
    if not url:
        return False
    return bool(re.match(r"^(https?://)?vk\.com/[\w.]+$", url.strip()))

def is_valid_tg_username(username: str) -> bool:
    if not username:
        return False
    if username.startswith('@'):
        username = username[1:]
    return bool(re.match(r"^[a-zA-Z0-9_]{5,32}$", username))

def is_valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()))
