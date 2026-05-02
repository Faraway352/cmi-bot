from sqlalchemy import (
    Column, Integer, String, BigInteger, Date, DateTime, Text,
    Boolean, ForeignKey, func
)
from sqlalchemy.dialects.postgresql import JSONB, INET
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    phone = Column(String(12))
    full_name = Column(String(150))
    gender = Column(String(3))
    birthday = Column(Date)
    role = Column(String(20), default='user')
    vk_url = Column(String(255))
    tg_username = Column(String(100))
    email = Column(String(150))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_archived = Column(Boolean, default=False)


class Event(Base):
    __tablename__ = 'events'

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    date_time = Column(DateTime(timezone=True), nullable=False)
    location = Column(String(255))
    participants_limit = Column(Integer)
    is_paid = Column(Boolean, default=False)
    vk_post_url = Column(String(255))
    status = Column(String(20), default='active')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_archived = Column(Boolean, default=False)


class Registration(Base):
    __tablename__ = 'registrations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    events_id = Column(Integer, ForeignKey('events.id'), nullable=False)
    status = Column(String(20), nullable=False, default='registered')
    queue_position = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    reminder_sent = Column(Boolean, default=False)          # <-- новое поле


class Feedback(Base):
    __tablename__ = 'feedbacks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    events_id = Column(Integer, ForeignKey('events.id'))
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class NotifySetting(Base):
    __tablename__ = 'notify_settings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    notification_type = Column(String(50))
    is_enabled = Column(Boolean, default=True)


class AdminAction(Base):
    __tablename__ = 'admin_actions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    action = Column(String(255), nullable=False)
    object_id = Column(Integer)
    payload = Column(JSONB)
    ip_address = Column(INET)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class BotMessage(Base):
    __tablename__ = 'bot_messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(50), nullable=False, unique=True)
    lang = Column(String(5))
    content = Column(Text, nullable=False)


class AuthCode(Base):
    __tablename__ = 'auth_codes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    code = Column(String(10), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_used = Column(Boolean, default=False)


class BroadcastHistory(Base):
    __tablename__ = 'broadcast_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    message_text = Column(Text, nullable=False)
    sent_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    status = Column(String(20), default='pending')
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class IntegrationLog(Base):
    __tablename__ = 'integration_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(255), default='vk_api')
    status = Column(String(20))
    response_data = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
