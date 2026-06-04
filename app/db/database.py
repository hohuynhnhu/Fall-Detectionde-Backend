from __future__ import annotations

import os
from typing import AsyncGenerator
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

load_dotenv()

_url: str | None = os.getenv("DATABASE_URL")
if not _url:
    raise RuntimeError("DATABASE_URL is not set in .env")

if _url.startswith("postgres://"):
    _url = _url.replace("postgres://", "postgresql+asyncpg://", 1)
elif _url.startswith("postgresql://") and "+asyncpg" not in _url:
    _url = _url.replace("postgresql://", "postgresql+asyncpg://", 1)

_parsed = urlparse(_url)
_qs = parse_qs(_parsed.query)
_qs.pop("sslmode", None)
_qs.pop("channel_binding", None)
_url = urlunparse(_parsed._replace(query=urlencode({k: v[0] for k, v in _qs.items()})))

DATABASE_URL: str = _url

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
    connect_args={"ssl": os.getenv("DB_SSL", "require")},
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    async with engine.begin() as conn:
        from . import models  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
        # Migrations for columns added after initial deploy
        await conn.execute(
            text("ALTER TABLE fall_events ADD COLUMN IF NOT EXISTS clip_url VARCHAR(512)")
        )
        await conn.execute(
            text("ALTER TABLE emergency_contacts ADD COLUMN IF NOT EXISTS relation VARCHAR(64)")
        )
        await conn.execute(
            text("ALTER TABLE emergency_contacts ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE")
        )
        await conn.execute(
            text("ALTER TABLE family_members ADD COLUMN IF NOT EXISTS user_id INTEGER")
        )
        await conn.execute(
            text("ALTER TABLE family_members ADD COLUMN IF NOT EXISTS is_patient BOOLEAN NOT NULL DEFAULT FALSE")
        )
        await conn.execute(
            text("ALTER TABLE family_members ADD COLUMN IF NOT EXISTS camera_id VARCHAR(32)")
        )
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(512)")
        )
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE")
        )
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(16) NOT NULL DEFAULT 'user'")
        )
        await conn.execute(
            text("ALTER TABLE family_members ADD COLUMN IF NOT EXISTS person_id VARCHAR(36)")
        )
        await conn.execute(
            text("ALTER TABLE family_members ADD COLUMN IF NOT EXISTS role VARCHAR(16)")
        )
        await conn.execute(
            text("ALTER TABLE family_members ADD COLUMN IF NOT EXISTS face_image_url VARCHAR(512)")
        )
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS face_recognition_logs ("
                "  id            SERIAL PRIMARY KEY,"
                "  user_id       INTEGER,"
                "  person_id     VARCHAR(36) NOT NULL,"
                "  name          VARCHAR(128) NOT NULL,"
                "  is_patient    BOOLEAN NOT NULL DEFAULT FALSE,"
                "  recognized_at FLOAT NOT NULL,"
                "  camera_id     VARCHAR(32) NOT NULL,"
                "  confidence    FLOAT"
                ")"
            )
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_face_recognition_logs_person_id "
                 "ON face_recognition_logs (person_id)")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_face_recognition_logs_recognized_at "
                 "ON face_recognition_logs (recognized_at)")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_face_recognition_logs_user_id "
                 "ON face_recognition_logs (user_id)")
        )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
