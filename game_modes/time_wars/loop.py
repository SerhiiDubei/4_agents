"""
TIME WARS game loop: tick, cooperate, steal, code use, scheduled events, finish.
Updates session state and event_log in TIMER-compatible format.
"""

from __future__ import annotations

import random
import time
from typing import Callable, Dict, List, Optional

from game_modes.time_wars.constants import (
    COOP_REWARD_EACH,
    STEAL_SUCCESS_ACTOR_GAIN,
    STEAL_SUCCESS_TARGET_LOSS,
    STEAL_PARTIAL_ACTOR_GAIN,
    STEAL_PARTIAL_TARGET_LOSS,
    STEAL_FAIL_ACTOR_PENALTY,
    STEAL_ROLL_SUCCESS_MIN,
    STEAL_ROLL_PARTIAL_MIN,
    EVENT_TYPE_COOPERATE,
    EVENT_TYPE_STEAL,
    EVENT_TYPE_SELF_ADD,
    EVENT_TYPE_CODE_USE,
    EVENT_TYPE_STORM,
    EVENT_TYPE_CRISIS,
    EVENT_TYPE_SKILL_TRIGGER,
    EVENT_TYPE_ELIMINATION,
    EVENT_TYPE_GAME_START,
    EVENT_TYPE_GAME_OVER,
    EVENT_TYPE_ROLE_ASSIGNMENT,
)
from game_modes.time_wars.state import Session, Player
from game_modes.time_wars import skills


def _log(session: Session, event: dict, tick: Optional[int] = None) -> None:
    if tick is not None:
        event["tick"] = tick
    event.setdefault("timestamp", time.time())
    session.event_log.append(event)


def _player_stats(session: Session, agent_id: str) -> dict:
    """Derive steal_count and coop_count from event_log."""
    steal_count = 0
    coop_count = 0
    for ev in session.event_log:
        if ev.get("event_type") == EVENT_TYPE_STEAL and ev.get("actor_id") == agent_id:
            steal_count += 1
        if ev.get("event_type") == EVENT_TYPE_COOPERATE and ev.get("actor_id") == agent_id:
            coop_count += 1
    return {"steal_count": steal_count, "coop_count": coop_count}


def tick(session: Session, tick_num: int) -> List[str]:
    """
    Decrease time_remaining_sec for all active players by 1. Eliminate at 0.
    Returns list of agent_ids eliminated this tick.
    """
    eliminated = []
    for p in session.players:
        if p.status != "active":
            continue
        p.time_remaining_sec = max(0, p.time_remaining_sec - 1)
        if p.time_remaining_sec <= 0:
            p.status = "eliminated"
            eliminated.append(p.agent_id)
            _log(session, {
                "event_type": EVENT_TYPE_ELIMINATION,
                "target_id": p.agent_id,
                "time_delta_seconds": 0,
            }, tick=tick_num)
    return eliminated


def apply_cooperate(session: Session, actor_id: str, target_id: str, tick_num: int) -> bool:
    """Both get +COOP_REWARD_EACH. Update trust. Log two events (one per player gain)."""
    pa = session.get_player(actor_id)
    pb = session.get_player(target_id)
    if not pa or not pb or pa.status != "active" or pb.status != "active":
        return False
    pa.time_remaining_sec += COOP_REWARD_EACH
    pb.time_remaining_sec += COOP_REWARD_EACH
    session.set_trust(actor_id, target_id, min(1.0, session.get_trust(actor_id, target_id) + 0.2))
    session.set_trust(target_id, actor_id, min(1.0, session.get_trust(target_id, actor_id) + 0.2))
    _log(session, {
        "event_type": EVENT_TYPE_COOPERATE,
        "actor_id": actor_id,
        "target_id": target_id,
        "time_delta_seconds": COOP_REWARD_EACH,
    }, tick=tick_num)
    return True


def apply_steal(
    session: Session,
    actor_id: str,
    target_id: str,
    tick_num: int,
    rng: Optional[random.Random] = None,
) -> dict:
    """
    Resolve steal: d20 + modifiers + skills. Apply time deltas. Log.
    Returns {"outcome": "success"|"partial"|"fail", "actor_delta": int, "target_delta": int, "skill_triggered": [...]}.
    """
    pa = session.get_player(actor_id)
    pb = session.get_player(target_id)
    if not pa or not pb or pa.status != "active" or pb.status != "active":
        return {"outcome": "fail", "actor_delta": 0, "target_delta": 0, "skill_triggered": []}
    if skills.block_steal(pa.role_id):
        return {"outcome": "blocked", "actor_delta": 0, "target_delta": 0, "skill_triggered": ["BLOCK"]}

    roll_bonus_result = skills.apply_before_steal_roll(pa.role_id, {
        "actor_id": actor_id,
        "target_id": target_id,
        "trust": session.get_trust(actor_id, target_id),
    })
    roll_bonus = roll_bonus_result.get("roll_bonus", 0)
    base_roll = (rng or random).randint(1, 20)
    total_roll = base_roll + roll_bonus

    skill_triggered = []
    if roll_bonus:
        skill_triggered.append("BEFORE_STEAL_ROLL")

    stats = _player_stats(session, actor_id)
    is_first_steal = stats["steal_count"] == 0
    first_steal_extra = skills.apply_on_first_steal_attempt(pa.role_id, {"is_first_steal": is_first_steal})
    extra_penalty = first_steal_extra.get("extra_penalty_time", 0)
    if extra_penalty:
        skill_triggered.append("ON_FIRST_STEAL_ATTEMPT")

    if total_roll >= STEAL_ROLL_SUCCESS_MIN:
        outcome = "success"
        actor_gain = STEAL_SUCCESS_ACTOR_GAIN
        target_loss = STEAL_SUCCESS_TARGET_LOSS
        success_eff = skills.apply_on_steal_success(pa.role_id, {})
        extra = success_eff.get("extra_time_stolen", 0)
        actor_gain += extra
        target_loss = min(pb.time_remaining_sec, target_loss + extra)
        if extra:
            skill_triggered.append("ON_STEAL_SUCCESS")
    elif total_roll >= STEAL_ROLL_PARTIAL_MIN:
        outcome = "partial"
        actor_gain = STEAL_PARTIAL_ACTOR_GAIN
        target_loss = STEAL_PARTIAL_TARGET_LOSS
    else:
        outcome = "fail"
        actor_gain = 0
        fail_eff = skills.apply_on_steal_fail(pa.role_id, {"default_penalty_seconds": STEAL_FAIL_ACTOR_PENALTY})
        penalty = fail_eff.get("penalty_override") if fail_eff.get("penalty_override") is not None else STEAL_FAIL_ACTOR_PENALTY
        actor_gain = -penalty - extra_penalty
        target_loss = 0
        if fail_eff.get("penalty_override") is not None or extra_penalty:
            skill_triggered.append("ON_STEAL_FAIL")

    pa.time_remaining_sec = max(0, pa.time_remaining_sec + actor_gain)
    pb.time_remaining_sec = max(0, pb.time_remaining_sec - target_loss)

    _log(session, {
        "event_type": EVENT_TYPE_STEAL,
        "actor_id": actor_id,
        "target_id": target_id,
        "time_delta_seconds": actor_gain,
        "outcome": outcome,
        "roll": total_roll,
        "skill_triggered": skill_triggered,
    }, tick=tick_num)
    if target_loss > 0:
        _log(session, {
            "event_type": EVENT_TYPE_STEAL,
            "actor_id": actor_id,
            "target_id": target_id,
            "time_delta_seconds": -target_loss,
            "target_effect": True,
        }, tick=tick_num)

    return {"outcome": outcome, "actor_delta": actor_gain, "target_delta": target_loss, "skill_triggered": skill_triggered}


def apply_code_use(session: Session, actor_id: str, code_index: int, tick_num: int) -> bool:
    """Consume code from inventory; apply base seconds; apply ON_CODE_USE (e.g. Banker 1.5x). Log."""
    pa = session.get_player(actor_id)
    if not pa or pa.status != "active" or code_index < 0 or code_index >= len(pa.inventory):
        return False
    code = pa.inventory.pop(code_index)
    base_sec = code.get("seconds", 30)
    mult_result = skills.apply_on_code_use(pa.role_id, {"actor_id": actor_id, "base_seconds": base_sec})
    mult = mult_result.get("code_time_multiplier", 1.0)
    final_sec = int(base_sec * mult)
    pa.time_remaining_sec += final_sec
    _log(session, {
        "event_type": EVENT_TYPE_CODE_USE,
        "actor_id": actor_id,
        "time_delta_seconds": final_sec,
        "code_id": code.get("code_id", ""),
        "base_seconds": base_sec,
        "multiplier": mult,
    }, tick=tick_num)
    return True


def run_storm(session: Session, tick_num: int, delta_sec: int = -30) -> None:
    """Apply storm: all active players lose delta_sec."""
    for p in session.active_players():
        p.time_remaining_sec = max(0, p.time_remaining_sec + delta_sec)
    _log(session, {
        "event_type": EVENT_TYPE_STORM,
        "time_delta_seconds": delta_sec,
        "affected": "all",
    }, tick=tick_num)


def run_crisis(session: Session, tick_num: int, threshold_sec: int = 300, penalty_sec: int = -60) -> None:
    """Players with time_remaining < threshold_sec lose penalty_sec."""
    for p in session.active_players():
        if p.time_remaining_sec < threshold_sec:
            p.time_remaining_sec = max(0, p.time_remaining_sec + penalty_sec)
    _log(session, {
        "event_type": EVENT_TYPE_CRISIS,
        "threshold_seconds": threshold_sec,
        "time_delta_seconds": penalty_sec,
    }, tick=tick_num)


def apply_game_end_bonuses(session: Session, tick_num: int) -> None:
    """Apply ON_GAME_END skills (e.g. Peacekeeper bonus for 0 steals)."""
    for p in session.active_players():
        stats = _player_stats(session, p.agent_id)
        ctx = {"steal_count": stats["steal_count"], "coop_count": stats["coop_count"]}
        result = skills.apply_on_game_end(p.role_id, ctx)
        bonus = result.get("bonus_seconds", 0)
        if bonus > 0:
            p.time_remaining_sec += bonus
            _log(session, {
                "event_type": EVENT_TYPE_SKILL_TRIGGER,
                "actor_id": p.agent_id,
                "skill_id": "ON_GAME_END",
                "time_delta_seconds": bonus,
            }, tick=tick_num)


def is_game_over(session: Session, current_tick: int) -> bool:
    """True if duration exceeded or only one (or zero) active left."""
    if current_tick >= session.duration_limit_sec:
        return True
    active = session.active_players()
    return len(active) <= 1


def log_game_start(session: Session) -> None:
    """Append game_start and role_assignment events."""
    _log(session, {
        "event_type": EVENT_TYPE_GAME_START,
        "session_id": session.session_id,
        "base_seconds_per_player": session.base_seconds_per_player,
        "duration_limit_sec": session.duration_limit_sec,
    })
    for p in session.players:
        _log(session, {
            "event_type": EVENT_TYPE_ROLE_ASSIGNMENT,
            "agent_id": p.agent_id,
            "role_id": p.role_id,
            "skills": [s.get("id") for s in skills.get_skills_for_role(p.role_id)],
            "cost": 0,
        })


def log_game_over(session: Session, tick_num: int, winner_id: Optional[str] = None) -> None:
    """Append game_over event."""
    _log(session, {
        "event_type": EVENT_TYPE_GAME_OVER,
        "tick": tick_num,
        "winner_id": winner_id,
        "final_times": {p.agent_id: p.time_remaining_sec for p in session.players},
    }, tick=tick_num)
