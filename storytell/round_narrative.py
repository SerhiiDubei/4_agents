"""
round_narrative.py — широкий опис раунду: що відбулося далі для кожного і всіх разом.

Генерує продовження історії, щоб не було розривів. Яскраво розкриває події.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from storytell.story_params import StoryParams


def _dn(agent_id: str, names: dict) -> str:
    return names.get(agent_id) or agent_id.split("_")[-1][:8]


def _action_label_uk(val: float) -> str:
    if val <= 0.2:
        return "зрадив"
    if val <= 0.45:
        return "майже зрадив"
    if val <= 0.75:
        return "частково підтримав"
    return "повністю підтримав"


def generate_round_narrative(
    round_num: int,
    total_rounds: int,
    actions: Dict[str, Dict[str, float]],
    payoffs: Dict[str, float],
    story_params: StoryParams,
    agent_names: dict,
    round_event_template: str = "",
    prev_rounds_narrative: str = "",
    agent_profiles: dict = None,
    model: str = "google/gemini-2.0-flash-001",
) -> str:
    """
    Генерує ШИРОКИЙ опис раунду через LLM: що відбулося для кожного і всіх разом.
    Продовжує історію, щоб не було розривів. Яскраво розкриває події.
    """
    from pipeline.seed_generator import call_openrouter

    names = agent_names or {}
    profiles = agent_profiles or {}

    def _coop(val):
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, dict):
            return float(val.get("cooperation", 0.5))
        return 0.5

    # Збираємо рішення: X зрадив/підтримав Y (use cooperation dimension)
    decisions = []
    for agent_id, targets in actions.items():
        aname = _dn(agent_id, names)
        for target_id, val in targets.items():
            if agent_id == target_id:
                continue
            tname = _dn(target_id, names)
            label = _action_label_uk(_coop(val))
            decisions.append(f"{aname} {label} {tname}")
    dec_str = "; ".join(decisions) if decisions else "—"

    # Payoffs
    sorted_pay = sorted(payoffs.items(), key=lambda x: -x[1])
    payoff_desc = ", ".join(f"{_dn(aid, names)}: {delta:+.2f}" for aid, delta in sorted_pay[:4])

    # Профілі для контексту
    profile_lines = []
    for aid, prof in profiles.items():
        if prof:
            pname = _dn(aid, names)
            conn = prof.get("connections", "")
            bio = prof.get("bio", "")[:80]
            if conn or bio:
                profile_lines.append(f"{pname}: {conn}. {bio}")
    profile_ctx = "\n".join(profile_lines) if profile_lines else ""

    system = (
        "Ти — сценарист драматичної історії. Пиши від третьої особи. Українською. "
        "Стиль: яскравий, кінематографічний. Опиши ЩО ВІДБУЛОСЬ ДАЛІ — для кожного персонажа і для всіх разом. "
        "Історія має продовжуватися без розривів. Мінімум 400 символів. Без діалогів — тільки опис подій."
    )

    user_parts = [
        f"Акт {round_num} з {total_rounds}. Контекст: {story_params.to_context_str()}",
        f"Подія раунду: {round_event_template or 'Вибір довіри.'}",
        f"Рішення: {dec_str}",
        f"Результати: {payoff_desc}",
    ]
    if profile_ctx:
        user_parts.insert(1, f"Персонажі:\n{profile_ctx}")
    if prev_rounds_narrative:
        user_parts.append(f"Що було раніше:\n{prev_rounds_narrative}")

    user = "\n\n".join(user_parts)
    user += (
        "\n\nОпиши ШИРОКО що відбулося в цьому акті: "
        "для кожного персонажа окремо (як вони пережили, що змінилося) і для всіх разом (атмосфера, напруга). "
        "Історія має плавно продовжуватися. Мінімум 400 символів."
    )

    try:
        return call_openrouter(
            system_prompt=system,
            user_prompt=user,
            model=model,
            temperature=0.8,
            max_tokens=600,
            timeout=90,
        ).strip()
    except Exception:
        return ""
