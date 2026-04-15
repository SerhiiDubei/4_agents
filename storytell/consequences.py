"""
consequences.py — наслідки після виборів у раунді.

Шаблонна генерація без LLM.
СЕР-8: Consequence Carryover — зрада в минулих раундах впливає на поточний текст.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from storytell.story_params import StoryParams


def _dn(agent_id: str, names: dict) -> str:
    return names.get(agent_id) or agent_id.split("_")[-1][:8]


def generate_consequences(
    round_num: int,
    actions_summary: Dict[str, Dict[str, float]],
    payoffs_summary: Dict[str, float],
    story_params: Optional[StoryParams] = None,
    names: dict = None,
    # СЕР-8: перенесення зрад з попередніх раундів
    betrayal_carryover: Optional[Dict[str, List[str]]] = None,
) -> str:
    """
    Повертає 1–3 речення наслідків після рішень.

    actions_summary: {agent_id: {target_id: action_value}}
    payoffs_summary: {agent_id: payoff_delta}
    betrayal_carryover: {agent_id: [target_ids кого зраджував раніше]} — СЕР-8
    """
    names = names or {}
    betrayal_carryover = betrayal_carryover or {}

    if not payoffs_summary:
        return ""

    sorted_by_payoff = sorted(payoffs_summary.items(), key=lambda x: -x[1])
    if not sorted_by_payoff:
        return ""

    winner_id, winner_delta = sorted_by_payoff[0]
    loser_id, loser_delta = sorted_by_payoff[-1]
    winner = _dn(winner_id, names)
    loser = _dn(loser_id, names)

    # Базовий результат поточного раунду
    parts: List[str] = []
    if winner_id == loser_id:
        parts.append("Після рішень: всі опинилися в однаковій ситуації.")
    elif loser_delta < 0:
        parts.append(f"Після рішень: {winner} отримав найбільше. {loser} втратив довіру.")
    else:
        parts.append(f"Після рішень: {winner} вийшов уперед. {loser} отримав менше.")

    # СЕР-8: якщо є зради з минулих раундів — додаємо контекст наслідків
    if betrayal_carryover:
        carryover_lines: List[str] = []
        for agent_id, past_targets in betrayal_carryover.items():
            if not past_targets:
                continue
            aname = _dn(agent_id, names)
            # Перевіряємо, чи поточні дії агента знову зраджують тих самих
            current_targets = actions_summary.get(agent_id, {})
            repeat_betrayals = []
            for t_id in past_targets:
                val = current_targets.get(t_id)
                if val is not None:
                    coop = float(val) if isinstance(val, (int, float)) else float(val.get("cooperation", 0.5))
                    if coop < 0.4:
                        repeat_betrayals.append(_dn(t_id, names))
            if repeat_betrayals:
                targets_str = ", ".join(repeat_betrayals)
                carryover_lines.append(
                    f"{aname} знову зрадив {targets_str} — ця закономірність вже не випадковість."
                )
            elif agent_id in [aid for aid, d in sorted_by_payoff[:2]]:
                # Раніше зраджував, але зараз нічого не зробив — тиша підозріла
                carryover_lines.append(
                    f"{aname} цього разу утримався — але пам'ять про минуле нікуди не ділась."
                )
        if carryover_lines:
            parts.extend(carryover_lines[:2])  # не більше 2 carryover-рядків

    return " ".join(parts)


def build_betrayal_carryover(
    all_round_actions: List[Dict[str, Dict[str, float]]],
    threshold: float = 0.4,
) -> Dict[str, List[str]]:
    """
    Будує словник зрад з УСІХ попередніх раундів.

    all_round_actions: список {agent_id: {target_id: coop_value}} для кожного раунду.
    Повертає {agent_id: [target_ids]} — кого агент зраджував хоча б раз.
    """
    carryover: Dict[str, List[str]] = {}
    for round_actions in all_round_actions:
        for agent_id, targets in round_actions.items():
            for target_id, val in targets.items():
                if agent_id == target_id:
                    continue
                coop = float(val) if isinstance(val, (int, float)) else float(val.get("cooperation", 0.5))
                if coop < threshold:
                    if agent_id not in carryover:
                        carryover[agent_id] = []
                    if target_id not in carryover[agent_id]:
                        carryover[agent_id].append(target_id)
    return carryover
