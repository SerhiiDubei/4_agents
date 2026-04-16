"""
logging_config.py — Централізована конфігурація logging для 4 Agents серверів.

Використання:
    from config.logging_config import setup_logging
    setup_logging()          # для продакшн-сервера
    setup_logging(debug=True) # для відлагодження

Рівні логування:
    DEBUG   — детальна інформація для відлагодження
    INFO    — нормальний хід гри (старт раунду, завершення фази)
    WARNING — несподівана але відновлювана ситуація (retry, fallback)
    ERROR   — помилка що вплинула на виконання (LLM failed, DB error)
    CRITICAL — критична помилка (не використовується зараз)
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional


def setup_logging(
    level: Optional[str] = None,
    debug: bool = False,
    fmt: Optional[str] = None,
) -> None:
    """
    Налаштовує root logger для всіх серверів.

    Args:
        level: рядковий рівень ("DEBUG", "INFO", "WARNING", "ERROR").
               Якщо не задано — зчитується з env LOG_LEVEL або дефолт INFO.
        debug: якщо True — форсує DEBUG рівень (зручно при запуску локально).
        fmt:   формат рядка логу. Якщо не задано — використовується стандартний.
    """
    # Визначити рівень: аргумент > env > дефолт
    if debug:
        resolved_level = logging.DEBUG
    else:
        env_level = os.environ.get("LOG_LEVEL", "").upper()
        resolved_level = getattr(logging, env_level, logging.INFO) if env_level else logging.INFO
        if level is not None:
            resolved_level = getattr(logging, level.upper(), logging.INFO)

    # Формат: [2026-04-16 21:04:05] INFO     island        Session started
    log_fmt = fmt or "[%(asctime)s] %(levelname)-8s %(name)-14s %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"

    # Перевіряємо чи root logger вже налаштований (щоб уникнути дублювання handlers)
    root = logging.getLogger()
    if root.handlers:
        return  # вже налаштований (наприклад uvicorn вже додав свій handler)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(resolved_level)
    handler.setFormatter(logging.Formatter(log_fmt, datefmt=date_fmt))

    root.setLevel(resolved_level)
    root.addHandler(handler)

    # Приглушуємо надмірний вивід сторонніх бібліотек
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Shortcut для отримання іменованого logger."""
    return logging.getLogger(name)
