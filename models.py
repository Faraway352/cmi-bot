from sqlalchemy import Column, Integer, String, BigInteger, Date, DateTime, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    phone = Column(String(20))
    first_name = Column(String(100))
    last_name = Column(String(100))
    gender = Column(String(10))
    birth_date = Column(Date)            # было age, теперь дата рождения
    role = Column(String(20), default='user')
    registered_at = Column(DateTime, server_default=func.now())
