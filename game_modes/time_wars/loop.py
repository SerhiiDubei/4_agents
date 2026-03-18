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
    COOP_MANA_EACH,
    STEAL_MANA_SUCCESS_ACTOR,
    STEAL_MANA_FAIL_ACTOR,
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
    EVENT_TYPE_CODE_BUY,
    EVENT_TYPE_STATE_SNAPSHOT,
    EVENT_TYPE_ROUND_START,
    EVENT_TYPE_PLAYER_INTENT,
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


def escalating_drain(tick_num: int, base: int = 1, double_every: int = 5) -> int:
    """
    Returns drain (seconds) for this tick.
    Doubles every `double_every` ticks: ticks 1-5 → base, 6-10 → base*2, 11-15 → base*4, ...
    """
    return base * (2 ** ((tick_num - 1) // double_every))


def tick(session: Session, tick_num: int, drain_sec: int = 1) -> List[str]:
    """
    Decrease time_remaining_sec for all active players by drain_sec. Eliminate at 0.
    Returns list of agent_ids eliminated this tick.
    drain_sec can escalate externally (e.g. via escalating_drain()).
    """
    eliminated = []
    for p in session.players:
        if p.status != "active":
            continue
        p.time_remaining_sec = max(0, p.time_remaining_sec - drain_sec)
        if p.time_remaining_sec <= 0:
            p.status = "eliminated"
            eliminated.append(p.agent_id)
            _log(session, {
                "event_type": EVENT_TYPE_ELIMINATION,
                "target_id": p.agent_id,
                "time_delta_seconds": -drain_sec,
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
    pa.mana = max(0, pa.mana + COOP_MANA_EACH)
    pb.mana = max(0, pb.mana + COOP_MANA_EACH)
    session.set_trust(actor_id, target_id, min(1.0, session.get_trust(actor_id, target_id) + 0.2))
    session.set_trust(target_id, actor_id, min(1.0, session.get_trust(target_id, actor_id) + 0.2))
    _log(session, {
        "event_type": EVENT_TYPE_COOPERATE,
        "actor_id": actor_id,
        "target_id": target_id,
        "time_delta_seconds": COOP_REWARD_EACH,
        "mana_actor_after": pa.mana,
        "mana_target_after": pb.mana,
        "trust_actor_target": session.get_trust(actor_id, target_id),
        "trust_target_actor": session.get_trust(target_id, actor_id),
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
    if outcome in ("success", "partial"):
        pa.mana = max(0, pa.mana + STEAL_MANA_SUCCESS_ACTOR)
    elif outcome == "fail":
        pa.mana = max(0, pa.mana + STEAL_MANA_FAIL_ACTOR)

    _log(session, {
        "event_type": EVENT_TYPE_STEAL,
        "actor_id": actor_id,
        "target_id": target_id,
        "time_delta_seconds": actor_gain,
        "outcome": outcome,
        "roll": total_roll,
        "skill_triggered": skill_triggered,
        "mana_actor_after": pa.mana,
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


def _resolve_card_effect(
    card: dict,
    choice_id: Optional[str],
    rng: Optional[random.Random],
) -> tuple[float, float, Optional[str]]:
    """
    Resolve choice and outcome from card. Returns (effect_self_min, effect_other_min, choice_id_used).
    effect in minutes; caller converts to seconds.
    """
    choices_list = card.get("choices", [])
    if not choices_list:
        return 0.0, 0.0, None
    rng = rng or random
    choice = None
    if choice_id:
        choice = next((c for c in choices_list if c.get("id") == choice_id), None)
    if not choice:
        choice = rng.choice(choices_list)
    choice_id_used = choice.get("id")
    outcomes = choice.get("outcomes", [])
    if not outcomes:
        return 0.0, 0.0, choice_id_used
    probs = [o.get("probability", 0) for o in outcomes]
    outcome = rng.choices(outcomes, weights=probs, k=1)[0]
    effect_self = float(outcome.get("effect_self", 0))
    effect_other = float(outcome.get("effect_other", 0))
    return effect_self, effect_other, choice_id_used


def apply_code_use(
    session: Session,
    actor_id: str,
    code_index: int,
    tick_num: int,
    target_id: Optional[str] = None,
    choice_id: Optional[str] = None,
    rng: Optional[random.Random] = None,
) -> bool:
    """
    Consume code from inventory. If card format (has choices): resolve choice/outcome, apply effect_self
    and effect_other (in minutes, converted to seconds). Legacy: code with "seconds" uses role multiplier.
    """
    pa = session.get_player(actor_id)
    if not pa or pa.status != "active" or code_index < 0 or code_index >= len(pa.inventory):
        return False
    code = pa.inventory.pop(code_index)

    # Card format: choices with outcomes (effect in minutes)
    if code.get("choices"):
        effect_self_min, effect_other_min, choice_id_used = _resolve_card_effect(code, choice_id, rng)
        effect_self_sec = int(effect_self_min * 60)
        effect_other_sec = int(effect_other_min * 60)
        # Apply role multiplier to positive self-gain (ON_CODE_USE — e.g. Banker 2x)
        if effect_self_sec > 0:
            mult_result = skills.apply_on_code_use(pa.role_id, {"actor_id": actor_id, "base_seconds": effect_self_sec})
            mult = mult_result.get("code_time_multiplier", 1.0)
            if mult != 1.0:
                effect_self_sec = int(effect_self_sec * mult)
        pa.time_remaining_sec = max(0, pa.time_remaining_sec + effect_self_sec)

        affected_ids: list[str] = []
        if code.get("target_all") and effect_other_sec != 0:
            # Apply effect_other to every active player except actor
            for other in session.active_players():
                if other.agent_id != actor_id:
                    other.time_remaining_sec = max(0, other.time_remaining_sec + effect_other_sec)
                    affected_ids.append(other.agent_id)
            target_id = "all"
        elif code.get("target_all_except_one") and effect_other_sec != 0:
            # Apply effect_other to every active player except actor and the chosen target_id
            if not target_id:
                others = [p.agent_id for p in session.active_players() if p.agent_id != actor_id]
                if others:
                    target_id = (rng or random).choice(others)
            for other in session.active_players():
                if other.agent_id != actor_id and other.agent_id != target_id:
                    other.time_remaining_sec = max(0, other.time_remaining_sec + effect_other_sec)
                    affected_ids.append(other.agent_id)
        else:
            # Single target
            need_target = code.get("target_other", False) and effect_other_min != 0
            if need_target and not target_id:
                others = [p.agent_id for p in session.active_players() if p.agent_id != actor_id]
                if others:
                    target_id = (rng or random).choice(others)
            if target_id and target_id != "all" and effect_other_sec != 0:
                pb = session.get_player(target_id)
                if pb and pb.status == "active":
                    pb.time_remaining_sec = max(0, pb.time_remaining_sec + effect_other_sec)
                    affected_ids.append(target_id)

        _log(session, {
            "event_type": EVENT_TYPE_CODE_USE,
            "actor_id": actor_id,
            "target_id": target_id,
            "affected_ids": affected_ids if len(affected_ids) > 1 else None,
            "code_id": code.get("id", ""),
            "choice_id": choice_id_used,
            "time_delta_seconds": effect_self_sec,
            "target_delta_seconds": effect_other_sec if affected_ids else None,
            "mana_actor_after": pa.mana,
        }, tick=tick_num)
        return True

    # Legacy: seconds + role multiplier
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
        "mana_actor_after": pa.mana,
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


def is_game_over(
    session: Session,
    current_tick: int,
    min_ticks_before_elimination_win: Optional[int] = None,
) -> bool:
    """
    True if only one (or zero) active players remain (battle royale — last one standing).
    Duration limit acts as hard cap only; the game ideally ends by elimination.
    """
    if current_tick >= session.duration_limit_sec:
        return True
    active = session.active_players()
    if len(active) <= 1:
        if min_ticks_before_elimination_win is None:
            return True
        return current_tick >= min_ticks_before_elimination_win
    return False


def log_game_start(session: Session, drain_double_every: int = 5) -> None:
    """Append game_start and role_assignment events."""
    _log(session, {
        "event_type": EVENT_TYPE_GAME_START,
        "session_id": session.session_id,
        "base_seconds_per_player": session.base_seconds_per_player,
        "duration_limit_sec": session.duration_limit_sec,
        "drain_double_every": drain_double_every,
        "mode": "battle_royale",
    })
    for p in session.players:
        _log(session, {
            "event_type": EVENT_TYPE_ROLE_ASSIGNMENT,
            "agent_id": p.agent_id,
            "role_id": p.role_id,
            "skills": [s.get("id") for s in skills.get_skills_for_role(p.role_id)],
            "cost": 0,
        })
    _log(session, {
        "event_type": EVENT_TYPE_STATE_SNAPSHOT,
        "players": [
            {
                "agent_id": p.agent_id,
                "time_remaining_sec": p.time_remaining_sec,
                "mana": p.mana,
                "role_id": p.role_id,
                "status": p.status,
            }
            for p in session.players
        ],
    })


def build_situation_text(session: Session, threshold_sec: int = 60) -> dict:
    """Return structured situation for round_start: is_tie, leader_id, leader_time_sec, below_count."""
    active = session.active_players()
    if not active:
        return {"is_tie": True, "leader_id": "", "leader_time_sec": 0, "below_count": 0}
    leader = max(active, key=lambda p: p.time_remaining_sec)
    times = {p.time_remaining_sec for p in active}
    is_tie = len(times) == 1
    below = sum(1 for p in active if p.time_remaining_sec < threshold_sec)
    return {
        "is_tie": is_tie,
        "leader_id": leader.agent_id,
        "leader_time_sec": leader.time_remaining_sec,
        "below_count": below,
        "below_threshold_sec": threshold_sec,
    }


def log_round_start(
    session: Session,
    round_num: int,
    tick_num: int,
    game_timer_sec: int,
    situation: dict,
) -> None:
    """Append round_start event: round number, tick, timer, players state, situation (structured)."""
    _log(session, {
        "event_type": EVENT_TYPE_ROUND_START,
        "round_num": round_num,
        "tick": tick_num,
        "game_timer_sec": game_timer_sec,
        "drain_sec": situation.get("drain_sec"),
        "drain_double_every": situation.get("drain_double_every"),
        "players": [
            {
                "agent_id": p.agent_id,
                "time_remaining_sec": p.time_remaining_sec,
                "mana": p.mana,
                "status": p.status,
            }
            for p in session.players
        ],
        "situation_tie": situation.get("is_tie", False),
        "situation_leader_id": situation.get("leader_id", ""),
        "situation_leader_time_sec": situation.get("leader_time_sec", 0),
        "situation_below_count": situation.get("below_count", 0),
        "situation_below_threshold": situation.get("below_threshold_sec", 60),
    }, tick=tick_num)


def log_player_intent(
    session: Session,
    agent_id: str,
    tick_num: int,
    thought: str = "",
    plan: str = "",
    choice: str = "",
    reason: str = "",
) -> None:
    """Append player_intent event before applying actions."""
    _log(session, {
        "event_type": EVENT_TYPE_PLAYER_INTENT,
        "agent_id": agent_id,
        "thought": thought or "",
        "plan": plan or "",
        "choice": choice or "",
        "reason": reason or "",
    }, tick=tick_num)


def log_code_buy(
    session: Session,
    agent_id: str,
    code_id: str,
    cost_mana: float,
    tick_num: int,
) -> None:
    """Append code_buy event after a successful purchase. mana_after is read from session."""
    pa = session.get_player(agent_id)
    mana_after = pa.mana if pa else 0
    _log(session, {
        "event_type": EVENT_TYPE_CODE_BUY,
        "agent_id": agent_id,
        "code_id": code_id,
        "cost_mana": cost_mana,
        "mana_after": mana_after,
    }, tick=tick_num)


def log_game_over(session: Session, tick_num: int, winner_id: Optional[str] = None) -> None:
    """Append game_over event. If winner_id is None and any player has time > 0, use max-time player."""
    if winner_id is None:
        with_time = [p for p in session.players if p.time_remaining_sec > 0]
        if with_time:
            winner_id = max(with_time, key=lambda p: p.time_remaining_sec).agent_id
    _log(session, {
        "event_type": EVENT_TYPE_GAME_OVER,
        "tick": tick_num,
        "winner_id": winner_id,
        "final_times": {p.agent_id: p.time_remaining_sec for p in session.players},
        "final_mana": {p.agent_id: p.mana for p in session.players},
    }, tick=tick_num)
