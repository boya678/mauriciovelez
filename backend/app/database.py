from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,
    pool_recycle=300,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Segunda BD (chat) ────────────────────────────────────────────
_engine2 = None
_SessionChat = None

if settings.DATABASE_URL_2:
    _engine2 = create_engine(
        settings.DATABASE_URL_2,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=300,
    )
    _SessionChat = sessionmaker(autocommit=False, autoflush=False, bind=_engine2)


def get_chat_db():
    if _SessionChat is None:
        raise HTTPException(status_code=503, detail="Chat DB no configurada")
    db = _SessionChat()
    try:
        yield db
    finally:
        db.close()
