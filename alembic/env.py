"""
Alembic environment — налаштований для 4_agents проекту.

Підтримує:
- SQLite (dev): sqlite:///timewars.db
- PostgreSQL (prod/Railway): DB_URL env var

Autogenerate: відстежує db/models.py (Base.metadata)
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Додаємо корінь проекту в sys.path щоб знайти db.*
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.database import DATABASE_URL
from db.models import Base

# Alembic config object
config = context.config

# Налаштування логування з alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Метадані моделей для autogenerate
target_metadata = Base.metadata

# Підставляємо реальний DATABASE_URL — перекриває заглушку в alembic.ini
config.set_main_option("sqlalchemy.url", DATABASE_URL)


def run_migrations_offline() -> None:
    """Offline mode: генерує SQL без з'єднання з БД (корисно для dry-run)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite не підтримує ALTER COLUMN — рендеримо batch operations
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Online mode: виконує міграції напряму через з'єднання."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite batch mode: дозволяє ALTER TABLE через recreate
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
