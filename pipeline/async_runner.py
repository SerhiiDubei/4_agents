"""
async_runner.py — безпечний запуск паралельних LLM-викликів (ВИС-10).

Проблема: game_engine.py повторював один і той самий аварійний патерн 3+ разів:
    loop = asyncio.get_event_loop()
    try:
        if loop.is_closed(): raise RuntimeError(...)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    results = loop.run_until_complete(...)

У Python 3.12 asyncio.get_event_loop() поза async-контекстом = RuntimeError.
Цей модуль надає чистий `run_parallel()` без цього антипатерну.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, Callable, Iterable, TypeVar

T = TypeVar("T")


def run_parallel(
    fn: Callable[..., T],
    items: Iterable[Any],
    *,
    max_workers: int | None = None,
) -> list[T]:
    """
    Запускає fn(item) паралельно для кожного item через asyncio.to_thread.

    Створює свій event loop на кожен виклик — ізольований і закритий після.
    Безпечно для Python 3.11+ і 3.12+.

    Args:
        fn: блокуюча функція що приймає один аргумент і повертає результат
        items: ітерабельний список аргументів
        max_workers: ліміт потоків (None = ThreadPoolExecutor default)

    Returns:
        Список результатів у тому ж порядку, що й items.

    Example:
        results = run_parallel(_gen_situation, agents)
    """
    items_list = list(items)
    if not items_list:
        return []

    async def _gather() -> list[T]:
        return list(await asyncio.gather(*[asyncio.to_thread(fn, item) for item in items_list]))

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_gather())
    finally:
        loop.close()


def run_parallel_named(
    fn: Callable[..., tuple[str, T]],
    items: Iterable[Any],
) -> dict[str, T]:
    """
    Як run_parallel, але fn повертає (key, value) — результат складається в dict.

    Зручно для паралельних LLM-викликів де fn = lambda agent: (agent.agent_id, ...).

    Args:
        fn: функція що повертає (str_key, value)
        items: агенти або інші об'єкти

    Returns:
        dict {key: value}
    """
    pairs = run_parallel(fn, items)
    return dict(pairs)
