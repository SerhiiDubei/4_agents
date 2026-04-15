"""
situation.py — опис ситуації для раунду.

Шаблонна генерація (generate_situation) + LLM-генерація per-agent (generate_situation_llm).
T5: generate_situation_llm приймає world_bible для єдиного тону між раундами.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from storytell.story_params import RoundEvent, StoryParams

if TYPE_CHECKING:
    from storytell.world_bible import WorldBible


def _dn(agent_id: str, names: dict) -> str:
    return names.get(agent_id) or agent_id.split("_")[-1][:8]


def generate_situation_llm(
    agent_id: str,
    round_num: int,
    total_rounds: int,
    story_params: StoryParams,
    round_event: RoundEvent,
    agent_names: dict,
    prev_rounds_summary: str = "",
    agent_profiles: dict = None,
    model: str = "google/gemini-2.0-flash-001",
    # T5: WorldBible для єдиного тону
    world_bible: Optional["WorldBible"] = None,
) -> str:
    """
    Генерує ситуацію для конкретного агента через LLM. Мінімум 500 символів.
    T5: якщо передано world_bible — системний промпт збагачується тоном/голосом/сенсорикою.
    """
    from pipeline.seed_generator import call_openrouter

    display_name = _dn(agent_id, agent_names or {})
    ev_desc = round_event.template.replace("{name}", "когось").replace("{name1}", "одного").replace("{name2}", "іншого").replace("{names}", "інших")

    # T5: базовий системний промпт збагачується WorldBible
    world_ctx = world_bible.to_system_context() if world_bible else ""
    # СЕР-5: жанр/настрій/ставки прямо в системному промпті
    style_hint = story_params.to_style_str()
    system_parts = [
        "Ти — сценарист. Пиши описово, від третьої особи. "
        "Стиль: атмосферний, кінематографічний. Українською. Тільки опис, без діалогів.",
        f"ТОН ТА ЖАНР: {style_hint}",
    ]
    if world_ctx:
        system_parts.append(f"\nБІБЛІЯ СВІТУ (дотримуйся цього стилю):\n{world_ctx}")
    system = "\n".join(system_parts)

    context = story_params.to_context_str()
    last_act_hint = ""
    if round_num == total_rounds:
        last_act_hint = " Останній акт — вибір на межі життя і смерті. Кожен має вирішити, кому довіритися в критичний момент."

    profile_ctx = ""
    if agent_profiles:
        lines = []
        for aid, prof in (agent_profiles or {}).items():
            if prof:
                pname = _dn(aid, agent_names or {})
                conn = prof.get("connections", "")
                prof_text = prof.get("profession", "")
                bio = (prof.get("bio", "") or "")[:60]
                if conn or prof_text or bio:
                    lines.append(f"{pname}: {conn}. {prof_text}. {bio}")
        if lines:
            profile_ctx = "Персонажі (зв'язки, професія, біо):\n" + "\n".join(lines) + "\n\n"

    user = (
        f"{profile_ctx}Персонаж: {display_name}. Акт {round_num} з {total_rounds}. Контекст: {context}\n"
        f"Подія цього акту: {ev_desc}{last_act_hint}\n"
    )
    if prev_rounds_summary:
        user += (
            f"Що вже сталося (рішення кожного + наслідки):\n{prev_rounds_summary}\n\n"
            "Історія має розвиватися саме з цих рішень — хто кого підтримав, хто зрадив, як це змінило атмосферу."
        )
    user += (
        "\n\nОпиши ситуацію для цього акту з погляду цього персонажа. "
        "Мінімум 500 символів. Що навколо, що сталося, атмосфера, напруга. Тільки опис."
    )

    return call_openrouter(
        system_prompt=system,
        user_prompt=user,
        model=model,
        temperature=0.85,
        max_tokens=450,
        timeout=90,
    ).strip()


def generate_situation(
    round_num: int,
    story_params: StoryParams,
    round_event: Optional[RoundEvent] = None,
    agent_names: dict = None,
) -> str:
    """
    Повертає 1–2 речення опису ситуації для раунду.

    round_event: опційно — якщо є, додає контекст події (generic, без імен).
    """
    parts = [f"{story_params.place}. {story_params.setup}. {story_params.problem}."]
    if round_event:
        # Generic version of event template (replace placeholders with neutral text)
        ev_desc = round_event.template
        ev_desc = ev_desc.replace("{name}", "когось").replace("{name1}", "одного").replace("{name2}", "іншого").replace("{names}", "інших")
        parts.append(ev_desc)
    return " ".join(parts)
