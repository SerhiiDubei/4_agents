"""
storytell — генеративний сторітейл для Island і Time Wars.

Окремий модуль від game engine. Ідея:
- Загальний сторітейл: рік, місце, дійові особи, проблема, завязка
- Кожен раунд — унікальна подія (напр. "ти береш X з собою на човен")
- Герої переживають ряд подій, де рішення (зрада/підтримка) мапляться на 1..N учасників

M3 зміни:
- СЕР-5: genre/mood/stakes → промпти LLM (to_style_str)
- СЕР-6: CharacterArcTracker — дуги персонажів між раундами
- СЕР-7: Dynamic Event Escalation — події ескалують по фазах гри
- СЕР-8: build_betrayal_carryover — зради переносяться в наступні раунди
- СЕР-9: Time Wars integration в serve_time_wars.py
"""

from storytell.story_params import StoryParams, RoundEvent
from storytell.story_generator import generate_story
from storytell.round_events import get_round_event, get_participants_for_event
from storytell.situation import generate_situation, generate_situation_llm
from storytell.consequences import generate_consequences, build_betrayal_carryover
from storytell.round_narrative import generate_round_narrative
from storytell.world_bible import WorldBible, generate_world_bible
from storytell.character_arc import CharacterArcTracker, CharacterArc

__all__ = [
    "StoryParams",
    "RoundEvent",
    "generate_story",
    "get_round_event",
    "get_participants_for_event",
    "generate_situation",
    "generate_situation_llm",
    "generate_consequences",
    "build_betrayal_carryover",
    "generate_round_narrative",
    "WorldBible",
    "generate_world_bible",
    "CharacterArcTracker",
    "CharacterArc",
]
