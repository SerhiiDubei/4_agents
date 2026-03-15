"""
consequences.py — наслідки після виборів у раунді.

Шаблонна генерація без LLM.
"""

from __future__ import annotations

from typing import Dict, Optional

from storytell.story_params import StoryParams


def _dn(agent_id: str, names: dict) -> str:
    return names.get(agent_id) or agent_id.split("_")[-1][:8]


def generate_consequences(
    round_num: int,
    actions_summary: Dict[str, Dict[str, float]],
    payoffs_summary: Dict[str, float],
    story_params: Optional[StoryParams] = None,
    names: dict = None,
) -> str:
    """
    Повертає 1–2 речення наслідків після рішень.

    actions_summary: {agent_id: {target_id: action_value}}
    payoffs_summary: {agent_id: payoff_delta}
    """
    names = names or {}
    if not payoffs_summary:
        return ""

    sorted_by_payoff = sorted(payoffs_summary.items(), key=lambda x: -x[1])
    if not sorted_by_payoff:
        return ""

    winner_id, winner_delta = sorted_by_payoff[0]
    loser_id, loser_delta = sorted_by_payoff[-1]
    winner = _dn(winner_id, names)
    loser = _dn(loser_id, names)

    if winner_id == loser_id:
        return f"Після рішень: всі опинилися в однаковій ситуації."
    if loser_delta < 0:
        return f"Після рішень: {winner} отримав найбільше. {loser} втратив довіру."
    return f"Після рішень: {winner} вийшов уперед. {loser} отримав менше."
