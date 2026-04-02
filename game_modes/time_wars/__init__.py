"""
TIME WARS — game mode: time as resource, ADD/Steal/Cooperate, roles with skills, codes (manifest).
Aligned with TIMER (rooms, players, events, codes) for future UI/integration.
"""

from game_modes.time_wars.constants import (
    DEFAULT_BASE_SECONDS_PER_PLAYER,
    DEFAULT_GAME_DURATION_SEC,
    COOP_REWARD_EACH,
    STEAL_SUCCESS_ACTOR_GAIN,
    STEAL_SUCCESS_TARGET_LOSS,
    STEAL_FAIL_ACTOR_PENALTY,
    EVENT_TYPE_COOPERATE,
    EVENT_TYPE_STEAL,
    EVENT_TYPE_SELF_ADD,
    EVENT_TYPE_ELIMINATION,
    EVENT_TYPE_GAME_START,
    EVENT_TYPE_GAME_OVER,
    EVENT_TYPE_ROLE_ASSIGNMENT,
    X_MANA_PER_MINUTE,
    CODE_CLASS_C,
    CODE_CLASS_B,
    CODE_CLASS_A,
    CODE_CLASS_S,
    RISK_LEVEL_MULTIPLIER,
)
from game_modes.time_wars.code_manifest import (
    TYPE_COEFFICIENTS,
    code_cost,
    base_ev_from_cost,
    segment_for_cost,
    validate_card,
)

__all__ = [
    "DEFAULT_BASE_SECONDS_PER_PLAYER",
    "DEFAULT_GAME_DURATION_SEC",
    "COOP_REWARD_EACH",
    "STEAL_SUCCESS_ACTOR_GAIN",
    "STEAL_SUCCESS_TARGET_LOSS",
    "STEAL_FAIL_ACTOR_PENALTY",
    "EVENT_TYPE_COOPERATE",
    "EVENT_TYPE_STEAL",
    "EVENT_TYPE_SELF_ADD",
    "EVENT_TYPE_ELIMINATION",
    "EVENT_TYPE_GAME_START",
    "EVENT_TYPE_GAME_OVER",
    "EVENT_TYPE_ROLE_ASSIGNMENT",
    "X_MANA_PER_MINUTE",
    "CODE_CLASS_C",
    "CODE_CLASS_B",
    "CODE_CLASS_A",
    "CODE_CLASS_S",
    "RISK_LEVEL_MULTIPLIER",
    "TYPE_COEFFICIENTS",
    "code_cost",
    "base_ev_from_cost",
    "segment_for_cost",
    "validate_card",
]
