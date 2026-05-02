import asyncio
from datetime import datetime, timedelta
from sqlalchemy import select, update
from config import async_session, BOT_TOKEN
from models import Event, Registration, User
from aiohttp import ClientSession

async def send_reminders():
    """Проверяет мероприятия, которые начнутся ровно через 24 часа, и рассылает напоминания."""
    now = datetime.now()
    window_start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=24)
    window_end = window_start + timedelta(hours=1)

    async with async_session() as session:
        # Находим мероприятия в нужном окне
        stmt = select(Event).where(
            Event.date_time >= window_start,
            Event.date_time < window_end,
            Event.status == 'active',
            Event.is_archived == False
        )
        events = (await session.execute(stmt)).scalars().all()

        for event in events:
            # Находим все регистрации, которым ещё не отправили напоминание
            reg_stmt = select(Registration).where(
                Registration.events_id == event.id,
                Registration.status == 'registered',
                Registration.reminder_sent == False
            )
            registrations = (await session.execute(reg_stmt)).scalars().all()

            ids_to_update = []
            for reg in registrations:
                user = await session.get(User, reg.user_id)
                if user:
                    text = (
                        f"⏰ Напоминание!\n\n"
                        f"Вы записаны на мероприятие «{event.title}»,\n"
                        f"которое состоится {event.date_time.strftime('%d.%m.%Y в %H:%M')}\n"
                        f"по адресу: {event.location or 'Не указан'}.\n\n"
                        f"Ждём вас!"
                    )
                    success = await send_telegram_message(user.telegram_id, text)
                    if success:
                        ids_to_update.append(reg.id)

            # Помечаем отправленные регистрации
            if ids_to_update:
                await session.execute(
                    update(Registration)
                    .where(Registration.id.in_(ids_to_update))
                    .values(reminder_sent=True)
                )
            await session.commit()

async def send_telegram_message(chat_id: int, text: str) -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    async with ClientSession() as session:
        try:
            async with session.post(url, json={"chat_id": chat_id, "text": text}) as resp:
                if resp.status == 200:
                    return True
                else:
                    print(f"Failed to send reminder to {chat_id}: {await resp.text()}")
                    return False
        except Exception as e:
            print(f"Error sending reminder to {chat_id}: {e}")
            return False

async def reminder_loop():
    """Бесконечный цикл, проверяющий напоминания каждые 30 минут."""
    while True:
        print("Проверка напоминаний...")
        await send_reminders()
        await asyncio.sleep(1800)  # 30 минут
