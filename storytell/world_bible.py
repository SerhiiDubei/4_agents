"""
world_bible.py — "Біблія світу" для Island.

Генерується ОДИН РАЗ на початку гри через LLM.
Відповідає на 12 питань: тон, голос, атмосфера, заборонені кліше,
сенсорна палітра, ключова метафора, драматична роль кожного агента.

Результат — WorldBible dataclass, що передається у всі narrative-функції
для єдиного тону впродовж всієї гри.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from storytell.story_params import StoryParams


@dataclass
class WorldBible:
    """
    Єдиний "голос" і атмосфера гри — генерується з seed + StoryParams + SOUL.md агентів.

    Всі поля — рядки що передаються в системні промпти narrative-функцій.
    """

    # 1. Тон і жанр (1-2 речення)
    tone: str = ""

    # 2. Голос оповідача (хто розповідає)
    narrator_voice: str = ""

    # 3. Заборонені кліше (кома-список)
    forbidden: str = ""

    # 4. Сенсорна палітра (звуки, запахи, освітлення)
    sensory: str = ""

    # 5. Темп і ритм розповіді
    pacing: str = ""

    # 6. Центральна метафора (що символізує гра)
    metaphor: str = ""

    # 7-12. Драматична роль кожного агента (agent_id → 1 речення)
    agent_roles: Dict[str, str] = field(default_factory=dict)

    # Повний world_context string для підстановки в промпти
    _context_cache: str = field(default="", repr=False)

    def to_system_context(self) -> str:
        """
        Компактний рядок для системного промпту narrative-функцій.
        Кешується після першого виклику.
        """
        if self._context_cache:
            return self._context_cache
        lines = []
        if self.tone:
            lines.append(f"ТОН: {self.tone}")
        if self.narrator_voice:
            lines.append(f"ГОЛОС ОПОВІДАЧА: {self.narrator_voice}")
        if self.forbidden:
            lines.append(f"ЗАБОРОНЕНО: {self.forbidden}")
        if self.sensory:
            lines.append(f"АТМОСФЕРА (сенсорика): {self.sensory}")
        if self.pacing:
            lines.append(f"ТЕМП: {self.pacing}")
        if self.metaphor:
            lines.append(f"МЕТАФОРА: {self.metaphor}")
        self._context_cache = "\n".join(lines)
        return self._context_cache

    def agent_role(self, agent_id: str) -> str:
        """Повертає драматичну роль агента або порожній рядок."""
        return self.agent_roles.get(agent_id, "")


def _extract_soul_voice(soul_md: str) -> str:
    """
    Витягує секцію Voice + Decision Instinct з SOUL.md (~150 chars кожна).
    Ці дві секції найкраще відображають "голос" персонажа.
    """
    if not soul_md:
        return ""
    lines = soul_md.split("\n")
    current_section = ""
    captured: List[str] = []
    target_sections = {"voice", "decision instinct", "голос", "рішення", "інстинкт"}

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("##"):
            section_name = stripped.lstrip("#").strip().lower()
            current_section = section_name
            continue
        if any(t in current_section for t in target_sections):
            if stripped:
                captured.append(stripped)
        if len("\n".join(captured)) >= 250:
            break

    return "\n".join(captured)[:300]


def generate_world_bible(
    story_params: StoryParams,
    agent_names: Dict[str, str],
    soul_mds: Optional[Dict[str, str]] = None,
    agent_profiles: Optional[Dict[str, dict]] = None,
    model: str = "google/gemini-2.0-flash-001",
) -> WorldBible:
    """
    Генерує WorldBible — один LLM-виклик на початку гри.

    Параметри:
        story_params   — базові параметри сторітейлу (місце, рік, проблема)
        agent_names    — {agent_id: display_name}
        soul_mds       — {agent_id: вміст SOUL.md} — для agent_roles
        agent_profiles — {agent_id: {bio, connections, profession}} — додатковий контекст
        model          — LLM модель

    Повертає WorldBible з єдиним тоном для всієї гри.
    Якщо LLM недоступний — повертає WorldBible з базовими значеннями.
    """
    try:
        return _generate_world_bible_llm(
            story_params, agent_names, soul_mds or {}, agent_profiles or {}, model
        )
    except Exception:
        return _generate_world_bible_fallback(story_params, agent_names, soul_mds or {})


def _generate_world_bible_llm(
    story_params: StoryParams,
    agent_names: Dict[str, str],
    soul_mds: Dict[str, str],
    agent_profiles: Dict[str, dict],
    model: str,
) -> WorldBible:
    from pipeline.seed_generator import call_openrouter

    names = agent_names or {}

    # Збираємо Voice-фрагменти з SOUL.md кожного агента
    soul_voices: List[str] = []
    for aid, soul in soul_mds.items():
        name = names.get(aid, aid.split("_")[-1][:8])
        voice = _extract_soul_voice(soul)
        if voice:
            soul_voices.append(f"[{name}] {voice[:200]}")

    soul_ctx = "\n".join(soul_voices[:6]) if soul_voices else ""

    context = story_params.to_context_str()
    agent_list = ", ".join(names.get(aid, aid) for aid in names)

    system = (
        "Ти — головний сценарист і режисер атмосфери. "
        "Відповідай ТІЛЬКИ валідним JSON-об'єктом без коментарів та без markdown-обгортки."
    )

    user = f"""Ти створюєш "Біблію Світу" для драматичної гри-симуляції.

КОНТЕКСТ ГРИ: {context}
ЖАНР: {story_params.genre} | НАСТРІЙ: {story_params.mood}
ПЕРСОНАЖІ: {agent_list}

{f"ГОЛОСИ ПЕРСОНАЖІВ (з їх Soul.md):{chr(10)}{soul_ctx}" if soul_ctx else ""}

Дай відповіді на 12 питань у форматі JSON:

{{
  "tone": "1-2 речення: загальний тон і жанровий регістр цієї конкретної гри",
  "narrator_voice": "1 речення: хто і як розповідає (напр: 'байдужий бог-спостерігач', 'виснажений журналіст', 'сама земля')",
  "forbidden": "кома-список 4-6 заборонених кліше та виразів яких треба уникати",
  "sensory": "2-3 речення: специфічна сенсорна палітра — що чути, що пахне, яке освітлення, яка текстура простору",
  "pacing": "1 речення: темп і ритм — рваний/плавний/наростаючий/задушливий",
  "metaphor": "1 речення: центральна метафора всієї гри (довіра як X, зрада як Y)",
  "agent_roles": {{
    {chr(10).join(f'"{aid}": "1 речення: драматична роль {names.get(aid, aid)} у цій конкретній історії"' for aid in list(names.keys())[:8])}
  }}
}}

Відповідай ТІЛЬКИ JSON. Без пояснень. Без markdown.
Пиши ТІЛЬКИ українською. Враховуй конкретних персонажів та їх голоси."""

    raw = call_openrouter(
        system_prompt=system,
        user_prompt=user,
        model=model,
        temperature=0.75,
        max_tokens=800,
        timeout=90,
    ).strip()

    # Очищуємо від можливого markdown
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    data = json.loads(raw)

    return WorldBible(
        tone=data.get("tone", ""),
        narrator_voice=data.get("narrator_voice", ""),
        forbidden=data.get("forbidden", ""),
        sensory=data.get("sensory", ""),
        pacing=data.get("pacing", ""),
        metaphor=data.get("metaphor", ""),
        agent_roles=data.get("agent_roles", {}),
    )


def _generate_world_bible_fallback(
    story_params: StoryParams,
    agent_names: Dict[str, str],
    soul_mds: Dict[str, str],
) -> WorldBible:
    """Детермінований fallback без LLM — на основі genre/mood."""
    genre_tone = {
        "thriller": "Холодний, напружений, без зайвих слів. Кожен рух може бути останнім.",
        "survival": "Виснажений і відчайдушний. Природа байдужа — люди ні.",
        "drama": "Людяний і важкий. Рішення болять, а наслідки залишаються.",
        "psychological": "Параноїдальний. Реальність викривлена підозрою і страхом.",
    }
    mood_sensory = {
        "tense": "Тиша переривається скрипом. Вологий холод. Напружене освітлення.",
        "desperate": "Запах поту і диму. Різке світло. Все рухається занадто повільно.",
        "hopeful": "Слабке тепле світло. Тихі голоси. Запах мокрої землі після дощу.",
        "paranoid": "Тіні скрізь. Кожен звук — загроза. Різкі контрасти темряви і світла.",
        "exhausted": "Притлумлені звуки. Сіре освітлення. Запах холодного металу.",
    }
    return WorldBible(
        tone=genre_tone.get(story_params.genre, "Драматичний і стриманий."),
        narrator_voice="Холодний свідок, що бачить все але не засуджує нікого.",
        forbidden="героїчні промови, щасливі випадковості, легкі рішення, штампи бойовика",
        sensory=mood_sensory.get(story_params.mood, "Темрява. Тиша. Напруга."),
        pacing="Повільно наростаючий, з різкими зупинками перед вибором.",
        metaphor=f"Довіра як єдина валюта в {story_params.place} — і вона закінчується.",
        agent_roles={aid: "" for aid in agent_names},
    )
