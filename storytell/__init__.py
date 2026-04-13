"""
storytell — генеративний сторітейл для Island.

Окремий модуль від game engine. Ідея:
- Загальний сторітейл: рік, місце, дійові особи, проблема, завязка
- Кожен раунд — унікальна подія (напр. "ти береш X з собою на човен")
- Герої переживають ряд подій, де рішення (зрада/підтримка) мапляться на 1..N учасників

Поки що без інтеграції в движок — тільки структура для подальшої reagregabльності.
"""

from storytell.story_params import StoryParams, RoundEvent
from storytell.story_generator import generate_story
from storytell.round_events import get_round_event, get_participants_for_event
from storytell.situation import generate_situation, generate_situation_llm
from storytell.consequences import generate_consequences
from storytell.round_narrative import generate_round_narrative
from storytell.world_bible import WorldBible, generate_world_bible

__all__ = [
    "StoryParams",
    "RoundEvent",
    "generate_story",
    "get_round_event",
    "get_participants_for_event",
    "generate_situation",
    "generate_situation_llm",
    "generate_consequences",
    "generate_round_narrative",
    "WorldBible",
    "generate_world_bible",
]
