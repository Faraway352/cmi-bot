async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # ... регистрация обработчиков (без изменений)

    # Создаём таблицы в БД
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # ВРЕМЕННО: вывести всех пользователей в лог
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT * FROM users"))
        rows = result.fetchall()
        print("=== ТЕКУЩИЕ ПОЛЬЗОВАТЕЛИ ===")
        for row in rows:
            print(dict(row._mapping))
        print("=== КОНЕЦ ===")

    # Устанавливаем команды бота (оставь как было)
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать/перезапустить")
    ])

    # Запускаем веб-сервер и поллинг параллельно
    await asyncio.gather(
        run_web_server(),
        dp.start_polling(bot)
    )
