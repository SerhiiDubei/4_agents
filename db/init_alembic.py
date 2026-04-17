"""
db/init_alembic.py

Ініціалізація Alembic при старті сервера.

Логіка:
- Якщо БД нова (немає alembic_version) І немає таблиць → `upgrade head` (повна міграція)
- Якщо БД нова (немає alembic_version) АЛЕ таблиці вже є → `stamp head` (прийняти як базову)
- Якщо alembic_version вже є → `upgrade head` (застосувати нові міграції)
"""

from __future__ import annotations

import logging

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from pathlib import Path

logger = logging.getLogger("db")

_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def _alembic_cfg() -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    return cfg


def run_migrations() -> None:
    """
    Викликати один раз при старті сервера.
    Безпечно: якщо схема вже актуальна — нічого не змінює.
    """
    from db.database import engine

    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        current_rev = ctx.get_current_revision()

    if current_rev is None:
        # Перевіряємо: таблиці вже існують?
        from db.database import engine as eng
        from sqlalchemy import inspect as sa_inspect
        existing = sa_inspect(eng).get_table_names()
        core_tables = {"users", "game_sessions", "player_actions"}

        if core_tables.issubset(set(existing)):
            # Існуюча БД без Alembic — ставимо stamp
            logger.info("db: існуюча БД, виконуємо alembic stamp head")
            command.stamp(_alembic_cfg(), "head")
        else:
            # Нова порожня БД — виконуємо повну міграцію
            logger.info("db: нова БД, виконуємо alembic upgrade head")
            command.upgrade(_alembic_cfg(), "head")
    else:
        # Alembic вже ініціалізований — застосовуємо нові міграції якщо є
        logger.info("db: alembic поточна ревізія=%s, перевіряємо upgrade", current_rev)
        command.upgrade(_alembic_cfg(), "head")
