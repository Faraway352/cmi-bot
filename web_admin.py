import os, secrets
from datetime import datetime, timedelta
from aiohttp import web, ClientSession
from sqlalchemy import select, func
from config import async_session, BOT_TOKEN
from models import User, Event, Feedback

SESSIONS = {}
PENDING_CODES = {}

def generate_token():
    return secrets.token_hex(32)

@web.middleware
async def error_middleware(request, handler):
    try:
        return await handler(request)
    except Exception as e:
        import traceback
        print("ERROR in admin panel:")
        traceback.print_exc()
        return web.Response(text=f"500 Internal Server Error\n\n{type(e).__name__}: {e}", status=500)

def require_admin(func):
    async def wrapper(request):
        token = request.cookies.get('admin_token')
        if not token or token not in SESSIONS:
            return web.HTTPFound('/admin')
        request['admin_tg_id'] = SESSIONS[token]
        return await func(request)
    return wrapper

def base_html(title, content):
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} — Админ-панель ЦМИ</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 min-h-screen">
    <nav class="bg-indigo-600 p-4 text-white flex justify-between">
        <span class="text-xl font-bold">ЦМИ Админ</span>
        <div>
            <a href="/admin/logout" class="underline">Выйти</a>
        </div>
    </nav>
    <div class="flex">
        <aside class="w-64 bg-white shadow-md min-h-screen p-4">
            <ul class="space-y-2">
                <li><a href="/admin/dashboard" class="block p-2 hover:bg-indigo-100 rounded">📊 Дашборд</a></li>
                <li><a href="/admin/users" class="block p-2 hover:bg-indigo-100 rounded">👥 Пользователи</a></li>
                <li><a href="/admin/events" class="block p-2 hover:bg-indigo-100 rounded">📋 Мероприятия</a></li>
                <li><a href="/admin/feedbacks" class="block p-2 hover:bg-indigo-100 rounded">💬 Отзывы</a></li>
                <li><a href="/admin/broadcast" class="block p-2 hover:bg-indigo-100 rounded">📢 Рассылка</a></li>
            </ul>
        </aside>
        <main class="flex-1 p-6">
            {content}
        </main>
    </div>
</body>
</html>"""

async def login_page(request):
    if request.cookies.get('admin_token') and request.cookies['admin_token'] in SESSIONS:
        return web.HTTPFound('/admin/dashboard')
    html = """<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8"><title>Вход в админ-панель</title>
<script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-gray-100 flex items-center justify-center h-screen">
<div class="bg-white p-8 rounded shadow-md w-96">
    <h1 class="text-2xl font-bold mb-4">Вход в админ-панель</h1>
    <form action="/admin/login" method="POST">
        <label class="block mb-2">Ваш Telegram ID (число):</label>
        <input type="text" name="tg_id" class="w-full border p-2 rounded" placeholder="123456789" required>
        <button type="submit" class="mt-4 w-full bg-indigo-600 text-white p-2 rounded">Получить код</button>
    </form>
</div></body></html>"""
    return web.Response(text=html, content_type='text/html')

async def login_send_code(request):
    data = await request.post()
    tg_id = data.get('tg_id')
    if not tg_id or not tg_id.isdigit():
        return web.Response(text="Неверный Telegram ID. <a href='/admin'>Назад</a>", content_type='text/html')
    tg_id = int(tg_id)
    async with async_session() as session:
        stmt = select(User).where(User.telegram_id == tg_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if not user or user.role != 'admin':
            return web.Response(text="Этот пользователь не администратор. <a href='/admin'>Назад</a>", content_type='text/html')
        code = str(secrets.randbelow(10**6)).zfill(6)
        PENDING_CODES[tg_id] = (code, datetime.now())
        try:
            await send_telegram_code(tg_id, code)
        except Exception as e:
            return web.Response(text=f"Ошибка отправки кода: {e}. <a href='/admin'>Назад</a>", content_type='text/html')
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Подтверждение</title>
<script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-gray-100 flex items-center justify-center h-screen">
<div class="bg-white p-8 rounded shadow-md w-96">
    <h1 class="text-xl font-bold mb-4">Код отправлен в Telegram</h1>
    <form action="/admin/verify" method="POST">
        <input type="hidden" name="tg_id" value="{tg_id}">
        <label class="block mb-2">Введите код:</label>
        <input type="text" name="code" class="w-full border p-2 rounded" required>
        <button type="submit" class="mt-4 w-full bg-green-600 text-white p-2 rounded">Войти</button>
    </form>
</div></body></html>"""
    return web.Response(text=html, content_type='text/html')

async def verify_code(request):
    data = await request.post()
    tg_id = int(data.get('tg_id'))
    code = data.get('code')
    if tg_id not in PENDING_CODES:
        return web.Response(text="Код не найден или истек. <a href='/admin'>Назад</a>", content_type='text/html')
    stored_code, timestamp = PENDING_CODES[tg_id]
    if datetime.now() - timestamp > timedelta(minutes=5):
        del PENDING_CODES[tg_id]
        return web.Response(text="Код истек. <a href='/admin'>Назад</a>", content_type='text/html')
    if code != stored_code:
        return web.Response(text="Неверный код. <a href='/admin'>Назад</a>", content_type='text/html')
    token = generate_token()
    SESSIONS[token] = tg_id
    del PENDING_CODES[tg_id]
    resp = web.HTTPFound('/admin/dashboard')
    resp.set_cookie('admin_token', token, max_age=3600, httponly=True)
    return resp

async def logout(request):
    token = request.cookies.get('admin_token')
    if token in SESSIONS:
        del SESSIONS[token]
    resp = web.HTTPFound('/admin')
    resp.del_cookie('admin_token')
    return resp

async def send_telegram_code(chat_id, code):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    async with ClientSession() as session:
        payload = {"chat_id": chat_id, "text": f"Ваш код для входа в админ-панель: {code}\nДействителен 5 минут."}
        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"Telegram API error: {text}")

# ---------- Дашборд ----------
@require_admin
async def dashboard(request):
    async with async_session() as session:
        users_count = await session.scalar(select(func.count(User.id)))
        events_count = await session.scalar(select(func.count(Event.id)).where(Event.is_archived == False))
        feedbacks_count = await session.scalar(select(func.count(Feedback.id)))
    content = f"""
    <h1 class="text-2xl font-bold mb-4">Дашборд</h1>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div class="bg-white p-4 rounded shadow">
            <h2 class="text-lg font-semibold">Пользователи</h2>
            <p class="text-3xl">{users_count}</p>
        </div>
        <div class="bg-white p-4 rounded shadow">
            <h2 class="text-lg font-semibold">Мероприятия</h2>
            <p class="text-3xl">{events_count}</p>
        </div>
        <div class="bg-white p-4 rounded shadow">
            <h2 class="text-lg font-semibold">Отзывы</h2>
            <p class="text-3xl">{feedbacks_count}</p>
        </div>
    </div>"""
    return web.Response(text=base_html("Дашборд", content), content_type='text/html')

# ---------- Пользователи ----------
@require_admin
async def users_list(request):
    page = int(request.query.get('page', 1))
    per_page = 20
    offset = (page - 1) * per_page
    async with async_session() as session:
        total = await session.scalar(select(func.count(User.id)))
        users = (await session.execute(select(User).order_by(User.id).offset(offset).limit(per_page))).scalars().all()
    rows = ""
    for u in users:
        rows += f"""<tr class="border-b">
            <td class="p-2 text-center">{u.id}</td>
            <td class="p-2 text-center">{u.full_name}</td>
            <td class="p-2 text-center">{u.telegram_id}</td>
            <td class="p-2 text-center">{u.phone}</td>
            <td class="p-2 text-center">{u.role}</td>
            <td class="p-2 text-center">{u.created_at.strftime('%d.%m.%Y') if u.created_at else ''}</td>
        </tr>"""
    content = f"""
    <h1 class="text-2xl font-bold mb-4">Пользователи</h1>
    <table class="w-full bg-white shadow rounded">
        <thead class="bg-gray-200"><tr><th class="p-2 text-center">ID</th><th class="p-2 text-center">ФИО</th><th class="p-2 text-center">Telegram ID</th><th class="p-2 text-center">Телефон</th><th class="p-2 text-center">Роль</th><th class="p-2 text-center">Дата рег.</th></tr></thead>
        <tbody>{rows}</tbody>
    </table>
    <div class="mt-4 flex gap-2">
        {f'<a href="/admin/users?page={page-1}" class="px-3 py-1 bg-gray-200 rounded">Назад</a>' if page > 1 else ''}
        {f'<a href="/admin/users?page={page+1}" class="px-3 py-1 bg-gray-200 rounded">Вперёд</a>' if page * per_page < total else ''}
    </div>"""
    return web.Response(text=base_html("Пользователи", content), content_type='text/html')

# ---------- Мероприятия ----------
@require_admin
async def events_list(request):
    page = int(request.query.get('page', 1))
    per_page = 10
    offset = (page - 1) * per_page
    async with async_session() as session:
        total = await session.scalar(select(func.count(Event.id)).where(Event.is_archived == False))
        events = (await session.execute(select(Event).where(Event.is_archived == False).order_by(Event.date_time.desc()).offset(offset).limit(per_page))).scalars().all()
    rows = ""
    for e in events:
        rows += f"""<tr class="border-b">
            <td class="p-2 text-center">{e.id}</td>
            <td class="p-2 text-center">{e.title}</td>
            <td class="p-2 text-center">{e.date_time.strftime('%d.%m.%Y %H:%M')}</td>
            <td class="p-2 text-center">{e.location}</td>
            <td class="p-2 text-center">{e.participants_limit}</td>
            <td class="p-2 text-center">{e.status}</td>
            <td class="p-2 text-center">
                <a href="/admin/events/edit/{e.id}" class="text-blue-600 underline">Ред.</a> |
                <a href="/admin/events/delete/{e.id}" class="text-red-600 underline" onclick="return confirm('Удалить?')">Удл.</a>
            </td>
        </tr>"""
    content = f"""
    <div class="flex justify-between mb-4">
        <h1 class="text-2xl font-bold">Мероприятия</h1>
        <a href="/admin/events/create" class="bg-green-600 text-white px-4 py-2 rounded">+ Создать</a>
    </div>
    <table class="w-full bg-white shadow rounded">
        <thead class="bg-gray-200"><tr><th class="p-2 text-center">ID</th><th class="p-2 text-center">Название</th><th class="p-2 text-center">Дата</th><th class="p-2 text-center">Место</th><th class="p-2 text-center">Лимит</th><th class="p-2 text-center">Статус</th><th class="p-2 text-center">Действия</th></tr></thead>
        <tbody>{rows}</tbody>
    </table>
    <div class="mt-4 flex gap-2">
        {f'<a href="/admin/events?page={page-1}" class="px-3 py-1 bg-gray-200 rounded">Назад</a>' if page > 1 else ''}
        {f'<a href="/admin/events?page={page+1}" class="px-3 py-1 bg-gray-200 rounded">Вперёд</a>' if page * per_page < total else ''}
    </div>"""
    return web.Response(text=base_html("Мероприятия", content), content_type='text/html')

@require_admin
async def event_create_form(request):
    content = """
    <h1 class="text-2xl font-bold mb-4">Создание мероприятия</h1>
    <form action="/admin/events/create" method="POST" class="bg-white p-6 rounded shadow max-w-lg">
        <label class="block mb-2">Название:</label><input type="text" name="title" class="w-full border p-2 rounded mb-2" required>
        <label class="block mb-2">Описание:</label><textarea name="description" class="w-full border p-2 rounded mb-2"></textarea>
        <label class="block mb-2">Дата и время (ГГГГ-ММ-ДД ЧЧ:ММ):</label><input type="text" name="datetime" placeholder="2026-07-01 15:00" class="w-full border p-2 rounded mb-2" required>
        <label class="block mb-2">Место:</label><input type="text" name="location" class="w-full border p-2 rounded mb-2">
        <label class="block mb-2">Лимит участников (0 - без ограничений):</label><input type="number" name="limit" value="0" class="w-full border p-2 rounded mb-2">
        <div class="flex items-center gap-2 mb-4">
            <label class="text-sm">Платное?</label>
            <input type="checkbox" name="is_paid" value="1">
        </div>
        <button type="submit" class="bg-blue-600 text-white px-4 py-2 rounded">Создать</button>
    </form>"""
    return web.Response(text=base_html("Новое мероприятие", content), content_type='text/html')

@require_admin
async def event_create(request):
    data = await request.post()
    try:
        dt = datetime.strptime(data['datetime'], "%Y-%m-%d %H:%M")
    except Exception:
        return web.Response(text="Неверный формат даты. <a href='/admin/events/create'>Назад</a>", content_type='text/html')
    async with async_session() as session:
        event = Event(
            title=data['title'], description=data.get('description'), date_time=dt,
            location=data.get('location'), participants_limit=int(data.get('limit', 0)),
            is_paid=bool(data.get('is_paid'))
        )
        session.add(event)
        await session.commit()
    return web.HTTPFound('/admin/events')

@require_admin
async def event_edit_form(request):
    event_id = int(request.match_info['id'])
    async with async_session() as session:
        event = await session.get(Event, event_id)
    if not event:
        return web.Response(text="Не найдено.", status=404)
    content = f"""
    <h1 class="text-2xl font-bold mb-4">Редактирование мероприятия #{event.id}</h1>
    <form action="/admin/events/edit/{event.id}" method="POST" class="bg-white p-6 rounded shadow max-w-lg">
        <label class="block mb-2">Название:</label><input type="text" name="title" value="{event.title}" class="w-full border p-2 rounded mb-2" required>
        <label class="block mb-2">Описание:</label><textarea name="description" class="w-full border p-2 rounded mb-2">{event.description or ''}</textarea>
        <label class="block mb-2">Дата и время (ГГГГ-ММ-ДД ЧЧ:ММ):</label><input type="text" name="datetime" value="{event.date_time.strftime('%Y-%m-%d %H:%M')}" class="w-full border p-2 rounded mb-2" required>
        <label class="block mb-2">Место:</label><input type="text" name="location" value="{event.location or ''}" class="w-full border p-2 rounded mb-2">
        <label class="block mb-2">Лимит:</label><input type="number" name="limit" value="{event.participants_limit}" class="w-full border p-2 rounded mb-2">
        <label class="block mb-2">Статус:</label>
        <select name="status" class="w-full border p-2 rounded mb-2">
            <option value="active" {'selected' if event.status == 'active' else ''}>Активно</option>
            <option value="cancelled" {'selected' if event.status == 'cancelled' else ''}>Отменено</option>
            <option value="finished" {'selected' if event.status == 'finished' else ''}>Завершено</option>
        </select>
        <div class="flex items-center gap-2 mb-4">
            <label class="text-sm">Платное?</label>
            <input type="checkbox" name="is_paid" value="1" {'checked' if event.is_paid else ''}>
        </div>
        <button type="submit" class="bg-blue-600 text-white px-4 py-2 rounded">Сохранить</button>
    </form>"""
    return web.Response(text=base_html("Редактирование", content), content_type='text/html')

@require_admin
async def event_edit_post(request):
    event_id = int(request.match_info['id'])
    data = await request.post()
    async with async_session() as session:
        event = await session.get(Event, event_id)
        if not event:
            return web.Response(text="Не найдено.", status=404)
        event.title = data['title']
        event.description = data.get('description')
        event.date_time = datetime.strptime(data['datetime'], "%Y-%m-%d %H:%M")
        event.location = data.get('location')
        event.participants_limit = int(data.get('limit', 0))
        event.status = data['status']
        event.is_paid = bool(data.get('is_paid'))
        await session.commit()
    return web.HTTPFound('/admin/events')

@require_admin
async def event_delete(request):
    event_id = int(request.match_info['id'])
    async with async_session() as session:
        event = await session.get(Event, event_id)
        if event:
            event.is_archived = True
            await session.commit()
    return web.HTTPFound('/admin/events')

# ---------- Отзывы ----------
@require_admin
async def feedbacks_list(request):
    page = int(request.query.get('page', 1))
    per_page = 10
    offset = (page - 1) * per_page
    async with async_session() as session:
        total = await session.scalar(select(func.count(Feedback.id)))
        feedbacks = (await session.execute(select(Feedback).order_by(Feedback.created_at.desc()).offset(offset).limit(per_page))).scalars().all()
    rows = ""
    for fb in feedbacks:
        async with async_session() as session:
            user = await session.get(User, fb.user_id)
            event = await session.get(Event, fb.events_id) if fb.events_id else None
        rows += f"""<tr class="border-b">
            <td class="p-2 text-center">{fb.id}</td>
            <td class="p-2 text-center">{user.full_name if user else 'Неизв.'}</td>
            <td class="p-2 text-center">{event.title if event else 'Центр'}</td>
            <td class="p-2 text-center">{fb.content[:100]}</td>
            <td class="p-2 text-center">{fb.created_at.strftime('%d.%m.%Y')}</td>
        </tr>"""
    content = f"""
    <h1 class="text-2xl font-bold mb-4">Отзывы</h1>
    <table class="w-full bg-white shadow rounded">
        <thead class="bg-gray-200"><tr><th class="p-2 text-center">ID</th><th class="p-2 text-center">Пользователь</th><th class="p-2 text-center">Мероприятие</th><th class="p-2 text-center">Текст</th><th class="p-2 text-center">Дата</th></tr></thead>
        <tbody>{rows}</tbody>
    </table>
    <div class="mt-4 flex gap-2">
        {f'<a href="/admin/feedbacks?page={page-1}" class="px-3 py-1 bg-gray-200 rounded">Назад</a>' if page > 1 else ''}
        {f'<a href="/admin/feedbacks?page={page+1}" class="px-3 py-1 bg-gray-200 rounded">Вперёд</a>' if page * per_page < total else ''}
    </div>"""
    return web.Response(text=base_html("Отзывы", content), content_type='text/html')

# ---------- Рассылка ----------
@require_admin
async def broadcast_form(request):
    content = """
    <h1 class="text-2xl font-bold mb-4">Рассылка сообщений</h1>
    <form action="/admin/broadcast" method="POST" class="bg-white p-6 rounded shadow max-w-lg">
        <label class="block mb-2">Текст сообщения:</label>
        <textarea name="message" rows="5" class="w-full border p-2 rounded mb-2" required></textarea>
        <button type="submit" class="bg-indigo-600 text-white px-4 py-2 rounded">Отправить всем</button>
    </form>"""
    return web.Response(text=base_html("Рассылка", content), content_type='text/html')

@require_admin
async def broadcast_send(request):
    data = await request.post()
    text = data['message']
    async with async_session() as session:
        users = (await session.execute(select(User.telegram_id))).scalars().all()
    sent = 0
    for uid in users:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            async with ClientSession() as http:
                await http.post(url, json={"chat_id": uid, "text": text})
                sent += 1
        except Exception:
            pass
    content = f"<p>Рассылка завершена. Отправлено {sent} из {len(users)}.</p><a href='/admin/dashboard'>Назад</a>"
    return web.Response(text=base_html("Результат рассылки", content), content_type='text/html')
