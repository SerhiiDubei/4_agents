"""
story_generator.py — генерація сторітейлу з random seed.

Детерміновано: seed → StoryParams.
Потім можна додати LLM-варіант для більш багатих описів.
"""

from __future__ import annotations

import random
from storytell.story_params import StoryParams

# Пресети для генерації (детерміновано по seed)
YEARS = [
    "1943", "1979", "сучасність", "2025", "невизначений час",
    "після катастрофи", "зима 1944", "літо 1991",
]

PLACES = [
    "острів у Тихому океані",
    "бункер під містом",
    "покинутий корабель",
    "гори Карпат",
    "занедбана база",
    "плот посеред моря",
    "підземелля",
    "затоплена долина",
]

PROBLEMS = [
    "ресурси закінчуються",
    "хтось може бути зрадником",
    "потрібно вирішити, хто йде першим",
    "один місць менше, ніж людей",
    "таємниця, яку хтось приховує",
    "конфлікт між двома групами",
    "недовіра після минулої зради",
    "обмежений доступ до води чи їжі",
]

SETUPS = [
    "корабель потонув, ви на плоту",
    "втеча з зони, де небезпечно",
    "шукаєте притулок разом",
    "поділили табір після катастрофи",
    "разом тримаєте оборону",
    "подорож до безпечного місця",
    "чекаєте рятувальників",
    "ділите останні запаси",
]

CHARACTER_SETS = [
    ["капітан", "медик", "штурман", "механік"],
    ["лідер", "розвідник", "постачальник", "охоронець"],
    ["старий", "молодий", "досвідчений", "новичок"],
    ["оптиміст", "реаліст", "параноїк", "дипломат"],
]

GENRES = ["drama", "survival", "thriller", "psychological"]
MOODS = ["tense", "desperate", "hopeful", "paranoid", "exhausted"]
STAKES = ["виживання", "втеча", "довіра", "честь", "справедливість", ""]


def generate_story(seed: int) -> StoryParams:
    """
    Генерує StoryParams з seed. Детерміновано — той самий seed дає той самий результат.
    """
    rng = random.Random(seed)

    year = rng.choice(YEARS)
    place = rng.choice(PLACES)
    problem = rng.choice(PROBLEMS)
    setup = rng.choice(SETUPS)
    characters = rng.choice(CHARACTER_SETS).copy()
    genre = rng.choice(GENRES)
    mood = rng.choice(MOODS)
    stakes = rng.choice(STAKES)

    return StoryParams(
        seed=seed,
        year=year,
        place=place,
        characters=characters,
        problem=problem,
        setup=setup,
        genre=genre,
        mood=mood,
        stakes=stakes,
    )
