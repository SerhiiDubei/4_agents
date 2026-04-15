"""
TIME WARS agent integration: build context for LLM (time, role, skills, others, events, inventory).
Action choice: COOPERATE (with whom), STEAL (from whom), PASS.
Code usage is handled separately in the CODE phase (loop.run_code_phase).

Decision making: utility-based model using CORE.json personality params + trust state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from game_modes.time_wars.state import Session
from game_modes.time_wars import skills
# When False: agents only use codes (CODE phase); ACTION phase = pass only
ACTION_COOPERATE_STEAL_ENABLED = True

# Role-based CORE overlays — імпортуємо з єдиного джерела правди (simulation/constants.py)
from simulation.constants import ROLE_CORE_OVERLAYS  # noqa: E402

from game_modes.time_wars.constants import (
    COOP_REWARD_EACH,
    STEAL_SUCCESS_ACTOR_GAIN,
    STEAL_PARTIAL_ACTOR_GAIN,
    STEAL_FAIL_ACTOR_PENALTY,
    STEAL_ROLL_SUCCESS_MIN,
    STEAL_ROLL_PARTIAL_MIN,
    EVENT_TYPE_COOPERATE,
    EVENT_TYPE_STEAL,
)


def _load_soul_md(agents_root: Optional[Path], agent_id: str) -> str:
    """Load full SOUL.md for agent. Returns empty string if file not found."""
    if not agents_root:
        agents_root = _default_agents_root()
    if not agents_root:
        return ""
    soul_path = agents_root / agent_id / "SOUL.md"
    if not soul_path.exists():
        return ""
    try:
        return soul_path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def build_context(
    session: Session,
    agent_id: str,
    agent_name: str = "",
    last_events_count: int = 10,
    last_messages: Optional[List[dict]] = None,
    agents_root: Optional[Path] = None,
) -> str:
    """
    Build a string context for the agent: own time, role, skills, others' times,
    last events, inventory, and comm-phase messages from this round.
    Includes SOUL.md personality profile (first 800 chars) when available.
    """
    p = session.get_player(agent_id)
    if not p:
        return ""
    role_skills = skills.get_skills_for_role(p.role_id)
    skill_names = [s.get("name", s.get("id", "")) for s in role_skills]
    others = []
    for o in session.players:
        if o.agent_id == agent_id or o.status != "active":
            continue
        trust_val = session.get_trust(agent_id, o.agent_id)
        others.append(f"  {o.agent_id}: {o.time_remaining_sec}s (trust={trust_val:.2f})")
    events_str = ""
    for ev in session.event_log[-last_events_count:]:
        et = ev.get("event_type", "")
        a = ev.get("actor_id", "")
        t = ev.get("target_id", "")
        d = ev.get("time_delta_seconds", 0)
        events_str += f"  [{et}] {a} -> {t} delta={d}\n"
    inv_str = ", ".join(c.get("id", "?") for c in p.inventory) if p.inventory else "empty"

    msgs_str = ""
    if last_messages:
        for m in last_messages[-6:]:
            ch = m.get("channel", "public")
            sender = m.get("sender_id", "?")
            text = m.get("text", "")
            msgs_str += f"  [{ch}] {sender}: {text}\n"

    # Load SOUL.md personality profile and prepend to context
    soul_md = _load_soul_md(agents_root, agent_id)
    soul_section = ""
    if soul_md:
        soul_section = f"PERSONALITY PROFILE (SOUL.md):\n{soul_md[:800]}\n\n"

    return (
        soul_section
        + f"You: {agent_name or agent_id}. Time left: {p.time_remaining_sec}s. Role: {p.role_id}. "
        f"Skills: {', '.join(skill_names)}.\n"
        f"Others:\n" + "\n".join(others) + "\n"
        f"Recent events:\n{events_str}"
        f"Inventory (codes): {inv_str}\n"
        + (f"Round messages:\n{msgs_str}" if msgs_str else "")
        + ("Choose: PASS (codes only mode)." if not ACTION_COOPERATE_STEAL_ENABLED
           else "Choose one action: COOPERATE <agent_id>, STEAL <agent_id>, or PASS.")
    )


def parse_action(response: str, agent_id: str, session: Session) -> Dict[str, Any]:
    """
    Parse agent response into action dict.
    response: raw LLM or mock response.
    Returns {"action": "cooperate"|"steal"|"pass", "target_id": str|None, "code_index": None}.
    use_code is no longer a valid action here — codes are handled in the CODE phase.
    """
    response = (response or "").strip().upper()
    if not response or "PASS" in response[:20]:
        return {"action": "pass", "target_id": None, "code_index": None}
    if "COOPERATE" in response:
        for p in session.players:
            if p.agent_id != agent_id and p.status == "active" and p.agent_id in response:
                return {"action": "cooperate", "target_id": p.agent_id, "code_index": None}
        return {"action": "pass", "target_id": None, "code_index": None}
    if "STEAL" in response:
        for p in session.players:
            if p.agent_id != agent_id and p.status == "active" and p.agent_id in response:
                return {"action": "steal", "target_id": p.agent_id, "code_index": None}
        return {"action": "pass", "target_id": None, "code_index": None}
    return {"action": "pass", "target_id": None, "code_index": None}


def _steal_ev(role_id: str, roll_bonus: int = 0) -> float:
    """
    Expected seconds gained from a steal attempt (ignoring target's state).
    EV = P(success)*gain + P(partial)*gain - P(fail)*penalty
    d20 roll: success >= STEAL_ROLL_SUCCESS_MIN, partial >= STEAL_ROLL_PARTIAL_MIN
    """
    total_faces = 20
    n_success = max(0, total_faces - STEAL_ROLL_SUCCESS_MIN + 1 + roll_bonus)
    n_partial = max(0, STEAL_ROLL_SUCCESS_MIN - STEAL_ROLL_PARTIAL_MIN - roll_bonus)
    n_fail = total_faces - n_success - n_partial
    n_success = max(0, min(total_faces, n_success))
    n_partial = max(0, min(total_faces - n_success, n_partial))
    n_fail = total_faces - n_success - n_partial

    ev = (
        (n_success / total_faces) * STEAL_SUCCESS_ACTOR_GAIN
        + (n_partial / total_faces) * STEAL_PARTIAL_ACTOR_GAIN
        - (n_fail / total_faces) * STEAL_FAIL_ACTOR_PENALTY
    )
    return ev


def _load_soul_voice(agents_root: Optional[Path], agent_id: str) -> str:
    """Load first ~150 chars of Decision Instinct or Voice from SOUL.md for template variation."""
    if not agents_root:
        return ""
    soul_path = agents_root / agent_id / "SOUL.md"
    if not soul_path.exists():
        return ""
    try:
        text = soul_path.read_text(encoding="utf-8")
        for header in ("## Decision Instinct", "## Voice"):
            if header in text:
                start = text.index(header) + len(header)
                chunk = text[start : start + 200].split("\n")[0].strip()
                return chunk[:150] if chunk else ""
    except Exception:
        pass
    return ""


def _summarize_messages_for_agent(
    last_messages: Optional[List[dict]],
    agent_id: str,
    agent_names: Optional[Dict[str, str]] = None,
) -> str:
    """Extract relevant context from COMM phase: who said what (to me in DM or publicly)."""
    if not last_messages:
        return ""
    name = lambda aid: (agent_names or {}).get(aid, aid) if agent_names else aid
    mentions_me = []
    for m in last_messages[-6:]:
        ch = m.get("channel", "public")
        sender = m.get("sender_id") or m.get("sender", "")
        text = (m.get("text") or "").strip()
        if not text:
            continue
        # channel "dm_{target_id}" = message sent TO target_id
        if ch.startswith("dm_") and ch == f"dm_{agent_id}":
            short = text[:55] + "…" if len(text) > 55 else text
            mentions_me.append(f"{name(sender)} (DM): «{short}»")
        elif ch == "public":
            short = text[:45] + "…" if len(text) > 45 else text
            mentions_me.append(f"{name(sender)}: {short}")
    if not mentions_me:
        return ""
    return " | ".join(mentions_me[-2:])  # last 2 messages


COOPERATION_LEVELS = (0.0, 0.33, 0.66, 1.0)  # як у main game (decision_engine)
COOPERATION_LABELS_UK = {
    0.0: "повна зрада",
    0.33: "м'яка зрада",
    0.66: "умовна кооперація",
    1.0: "повна кооперація",
}


def _get_observed_actions_from_event_log(
    session: Session,
    observer_id: str,
    prev_round_tick: Optional[int] = None,
) -> Dict[str, float]:
    """
    Extract per-target observed actions from event_log (prev round cooperate/steal).
    For observer_id: what did each other agent do toward us? cooperate→0.66/1.0, steal→0.0/0.33.
    """
    observed: Dict[str, float] = {}
    others = [o.agent_id for o in session.active_players() if o.agent_id != observer_id]
    for oid in others:
        observed[oid] = 0.5  # default
    if prev_round_tick is None:
        return observed
    for ev in session.event_log:
        if ev.get("tick") != prev_round_tick:
            continue
        et = ev.get("event_type", "")
        actor = ev.get("actor_id", "")
        target = ev.get("target_id", "")
        if actor not in others and actor != observer_id:
            continue
        if et == EVENT_TYPE_COOPERATE:
            if actor == observer_id:
                continue  # we observe others, not ourselves
            if target == observer_id:
                observed[actor] = 0.66  # they cooperated with us
            else:
                observed[actor] = 0.5  # they cooperated with someone else
        elif et == EVENT_TYPE_STEAL and not ev.get("target_effect"):
            if actor == observer_id:
                continue
            if target == observer_id:
                observed[actor] = 0.0  # they stole from us
            else:
                observed[actor] = 0.33  # they stole from someone else (deceptive)
    return observed


def _get_cooperation_levels_per_target(
    session: Session,
    agent_id: str,
    round_num: int = 1,
    total_rounds: int = 30,
    last_messages: Optional[List[dict]] = None,
    rng: Optional[Any] = None,
    current_tick: Optional[int] = None,
    ticks_per_action: int = 10,
) -> Dict[str, float]:
    """
    Per-target cooperation levels (0/0.33/0.66/1.0) як у main game.
    Returns {target_id: level} for each other active player.
    """
    try:
        from pipeline.decision_engine import choose_action, CoreParams, AgentContext
    except ImportError:
        p = session.get_player(agent_id)
        if not p:
            return {}
        cb = p.cooperation_bias()
        default = 0.66 if cb > 0.5 else 0.33
        return {o.agent_id: default for o in session.active_players() if o.agent_id != agent_id}

    p = session.get_player(agent_id)
    if not p:
        return {}
    others = [o for o in session.active_players() if o.agent_id != agent_id]
    if not others:
        return {}

    # Base CORE params from agent's stored personality
    _mods = ROLE_CORE_OVERLAYS.get(p.role_id, {})
    core = CoreParams(
        cooperation_bias=max(0.0, min(100.0, float(p.core_params.get("cooperation_bias", 50)) + _mods.get("cooperation_bias", 0))),
        deception_tendency=max(0.0, min(100.0, float(p.core_params.get("deception_tendency", 50)) + _mods.get("deception_tendency", 0))),
        strategic_horizon=max(0.0, min(100.0, float(p.core_params.get("strategic_horizon", 50)) + _mods.get("strategic_horizon", 0))),
        risk_appetite=max(0.0, min(100.0, float(p.core_params.get("risk_appetite", 50)) + _mods.get("risk_appetite", 0))),
    )

    prev_tick = (current_tick - ticks_per_action) if current_tick and current_tick > ticks_per_action else None
    observed = _get_observed_actions_from_event_log(session, agent_id, prev_tick)

    # Build reasoning_hint from comm messages: DMs first (strong signal), then public (weaker)
    reasoning_hint = ""
    if last_messages:
        for m in last_messages[-8:]:
            ch = m.get("channel", "public")
            text = (m.get("text") or "").strip()
            if not text:
                continue
            if ch == f"dm_{agent_id}":
                reasoning_hint = text + " " + reasoning_hint  # DMs prepended (higher priority)
            elif ch == "public" and len(reasoning_hint) < 400:
                reasoning_hint += text[:80] + " "

    result: Dict[str, float] = {}
    for other in others:
        per_target_context = AgentContext(
            round_number=round_num,
            total_rounds=total_rounds,
            trust_scores={other.agent_id: session.get_trust(agent_id, other.agent_id)},
            observed_actions={other.agent_id: observed.get(other.agent_id, 0.5)},
            betrayals_received=0,
            cooperations_received=0,
            reasoning_hint=reasoning_hint[:500],
        )
        seed = rng.randint(0, 2**31 - 1) if rng and hasattr(rng, "randint") else None
        res = choose_action(core, per_target_context, seed=seed, dim_id="cooperation")
        result[other.agent_id] = float(res.action)
    return result


def _get_cooperation_level(
    session: Session,
    agent_id: str,
    round_num: int = 1,
    total_rounds: int = 30,
    last_messages: Optional[List[dict]] = None,
    rng: Optional[Any] = None,
) -> float:
    """
    Використовує decision_engine (0, 0.33, 0.66, 1.0) — як у main game.
    Повертає обраний рівень кооперації/зради.
    """
    try:
        from pipeline.decision_engine import (
            choose_action,
            CoreParams,
            AgentContext,
        )
    except ImportError:
        p = session.get_player(agent_id)
        if not p:
            return 0.5
        cb = p.cooperation_bias()
        return 0.66 if cb > 0.5 else 0.33  # fallback

    p = session.get_player(agent_id)
    if not p:
        return 0.5

    _mods2 = ROLE_CORE_OVERLAYS.get(p.role_id, {})
    core = CoreParams(
        cooperation_bias=max(0.0, min(100.0, float(p.core_params.get("cooperation_bias", 50)) + _mods2.get("cooperation_bias", 0))),
        deception_tendency=max(0.0, min(100.0, float(p.core_params.get("deception_tendency", 50)) + _mods2.get("deception_tendency", 0))),
        strategic_horizon=max(0.0, min(100.0, float(p.core_params.get("strategic_horizon", 50)) + _mods2.get("strategic_horizon", 0))),
        risk_appetite=max(0.0, min(100.0, float(p.core_params.get("risk_appetite", 50)) + _mods2.get("risk_appetite", 0))),
    )

    trust_scores = {}
    observed_actions = {}
    for o in session.active_players():
        if o.agent_id == agent_id:
            continue
        trust_scores[o.agent_id] = session.get_trust(agent_id, o.agent_id)
        observed_actions[o.agent_id] = 0.5  # default

    mem = getattr(session, "memory_summary", None) or {}
    betrayals = mem.get("betrayals_received", 0) if isinstance(mem, dict) else 0
    cooperations = mem.get("cooperations_received", 0) if isinstance(mem, dict) else 0

    reasoning_hint = ""
    if last_messages:
        for m in last_messages[-8:]:
            ch = m.get("channel", "public")
            text = (m.get("text") or "").strip()
            if not text:
                continue
            if ch == f"dm_{agent_id}":
                reasoning_hint = text + " " + reasoning_hint
            elif ch == "public" and len(reasoning_hint) < 400:
                reasoning_hint += text[:80] + " "

    context = AgentContext(
        round_number=round_num,
        total_rounds=total_rounds,
        trust_scores=trust_scores,
        observed_actions=observed_actions,
        betrayals_received=betrayals,
        cooperations_received=cooperations,
        reasoning_hint=reasoning_hint[:500],
    )

    seed = None
    if rng is not None and hasattr(rng, "randint"):
        seed = rng.randint(0, 2**31 - 1)

    result = choose_action(core, context, seed=seed, dim_id="cooperation")
    return float(result.action)


def _pick_template(variants: List[str], agent_id: str, voice: str) -> str:
    """Pick stable variant per agent to get varied but consistent personality."""
    seed = hash(agent_id + voice[:80]) & 0x7FFFFFFF
    return variants[seed % len(variants)]


def _default_agents_root() -> Optional[Path]:
    """Project root / agents for SOUL loading when not passed."""
    root = Path(__file__).resolve().parent.parent.parent / "agents"
    return root if root.exists() else None


def _format_levels_suffix(
    cooperation_levels: Optional[Dict[str, float]] = None,
    agent_names: Optional[Dict[str, str]] = None,
) -> str:
    """Format per-target positions: 'До Марти: 0.66, до Вови: 0.33'."""
    if not cooperation_levels:
        return ""
    name = lambda aid: (agent_names or {}).get(aid, aid) if agent_names else aid
    parts = [f"до {name(tid)}: {lev:.2f}" for tid, lev in sorted(cooperation_levels.items())]
    return " [" + ", ".join(parts) + "]"


def _build_intent_text(
    action: str,
    target_id: Optional[str],
    agent_id: str,
    agent_names: Optional[Dict[str, str]] = None,
    last_messages: Optional[List[dict]] = None,
    agents_root: Optional[Path] = None,
    cooperation_level: Optional[float] = None,
    cooperation_levels_per_target: Optional[Dict[str, float]] = None,
) -> tuple[str, str, str, str]:
    """Build thought, plan, choice, reason in Ukrainian with context."""
    if agents_root is None:
        agents_root = _default_agents_root()
    name = lambda aid: (agent_names or {}).get(aid, aid) if agent_names else aid
    target_name = name(target_id) if target_id else ""
    voice = _load_soul_voice(agents_root, agent_id)
    ctx = _summarize_messages_for_agent(last_messages, agent_id, agent_names)

    prefix = ""
    if ctx:
        prefix = f"Розмова раунду: {ctx}. "

    level_suffix = _format_levels_suffix(cooperation_levels_per_target, agent_names)
    if not level_suffix and cooperation_level is not None:
        lbl = COOPERATION_LABELS_UK.get(cooperation_level, f"{cooperation_level:.2f}")
        level_suffix = f" [рівень: {cooperation_level:.2f} — {lbl}]"

    if action == "cooperate" and target_id:
        thoughts = [
            "Хочу підсилити союзника.",
            "Бачу сенс у співпраці.",
            "Разом краще — обираю кооперацію.",
            "Ціную партнерство.",
        ]
        thought = prefix + _pick_template(thoughts, agent_id, voice)
        plan = f"Кооперую з {target_name}.{level_suffix}"
        choice = f"Кооперація з {target_name}.{level_suffix}"
        reason = f"Взаємна вигода.{level_suffix}" if level_suffix else "Взаємна вигода."
    elif action == "steal" and target_id:
        thoughts = [
            "Ризикую забрати час.",
            "Потрібен час — готовий до ризику штрафу.",
            "Мушу підсилитися за чужій рахунок.",
        ]
        thought = prefix + _pick_template(thoughts, agent_id, voice)
        plan = f"Краду у {target_name}.{level_suffix}"
        choice = f"Крадіжка у {target_name}.{level_suffix}"
        reason = f"Потрібен час; готовий до ризику штрафу.{level_suffix}" if level_suffix else "Потрібен час; готовий до ризику штрафу."
    else:
        thoughts = [
            "Лише коди цього раунду — пасую.",
            "Коди дають достатньо. Пас.",
            "Нічого не робити в ACTION.",
        ]
        thought = prefix + _pick_template(thoughts, agent_id, voice)
        plan = f"Пас.{level_suffix}"
        choice = f"Пас.{level_suffix}"
        reason = f"Коди вже застосовані в CODE phase.{level_suffix}" if level_suffix else "Коди вже застосовані в CODE phase."

    return thought, plan, choice, reason


def compute_action_utility(
    session: Session,
    agent_id: str,
) -> tuple[str, Optional[str]]:
    """
    Utility-based action selection. When ACTION_COOPERATE_STEAL_ENABLED is False,
    always returns pass — agents use only codes for now.
    """
    if not ACTION_COOPERATE_STEAL_ENABLED:
        return "pass", None

    p = session.get_player(agent_id)
    if not p:
        return "pass", None

    others = [o for o in session.active_players() if o.agent_id != agent_id]
    if not others:
        return "pass", None

    can_steal = not skills.block_steal(p.role_id)
    coop_bias = p.cooperation_bias()        # 0.0–1.0
    deceit = p.deception_tendency()         # 0.0–1.0
    risk = p.risk_appetite()                # 0.0–1.0

    # Time pressure: the lower our time relative to base, the more urgent actions are
    base_sec = session.base_seconds_per_player or 1000
    time_ratio = p.time_remaining_sec / base_sec  # 0..1+
    in_danger = time_ratio < 0.25

    # Roll bonus from skills
    roll_bonus_result = skills.apply_before_steal_roll(p.role_id, {
        "actor_id": agent_id, "target_id": "", "trust": 0.5
    })
    roll_bonus = roll_bonus_result.get("roll_bonus", 0)
    ev_steal_base = _steal_ev(p.role_id, roll_bonus)

    best_action: str = "pass"
    best_target: Optional[str] = None
    best_util: float = 2.0  # pass baseline; slightly higher when safe, lower when in danger

    if in_danger:
        best_util = 0.5  # urgently look for something better

    # Evaluate cooperate for each target
    for o in others:
        trust = session.get_trust(agent_id, o.agent_id)
        # Cooperation utility: both gain, scaled by how cooperative we are and trust
        # When in danger, cooperating is less valuable (we need bigger gains)
        coop_util = COOP_REWARD_EACH * coop_bias * (0.5 + trust * 0.5)
        if in_danger:
            coop_util *= 0.6  # less useful when desperate

        if coop_util > best_util:
            best_util = coop_util
            best_action = "cooperate"
            best_target = o.agent_id

    # Evaluate steal for each target
    if can_steal:
        for o in others:
            trust = session.get_trust(agent_id, o.agent_id)
            # More likely to steal from rich players, from those we distrust
            target_ratio = o.time_remaining_sec / base_sec
            steal_util = ev_steal_base * deceit * (1.0 - trust * 0.5) * (0.5 + target_ratio * 0.5)
            if in_danger:
                steal_util *= (1.0 + risk)  # risk-appetite boosts steal when desperate

            if steal_util > best_util:
                best_util = steal_util
                best_action = "steal"
                best_target = o.agent_id

    return best_action, best_target


def get_agent_action_mock(
    session: Session,
    agent_id: str,
    rng: Optional[Any] = None,
    last_messages: Optional[List[dict]] = None,
    agent_names: Optional[Dict[str, str]] = None,
    agents_root: Optional[Path] = None,
    round_num: Optional[int] = None,
    total_rounds: int = 30,
    current_tick: Optional[int] = None,
    ticks_per_action: int = 10,
) -> Dict[str, Any]:
    """
    Per-target cooperation levels (0/0.33/0.66/1.0) + action selection.
    level >= 0.66 → cooperate; level <= 0.33 + can_steal → steal; else pass/utility fallback.
    Mana replenishes via apply_cooperate (+5 each).
    """
    import random as _random
    rng = rng or _random
    rnd = round_num if round_num is not None else 1
    p = session.get_player(agent_id)
    others = [o for o in session.active_players() if o.agent_id != agent_id]

    cooperation_levels = _get_cooperation_levels_per_target(
        session, agent_id, round_num=rnd, total_rounds=total_rounds,
        last_messages=last_messages, rng=rng,
        current_tick=current_tick, ticks_per_action=ticks_per_action,
    ) if others else {}

    thought, plan, choice, reason = _build_intent_text(
        "pass", None, agent_id,
        agent_names=agent_names,
        last_messages=last_messages,
        agents_root=agents_root,
        cooperation_levels_per_target=cooperation_levels,
    )

    if not ACTION_COOPERATE_STEAL_ENABLED:
        return {
            "action": "pass",
            "target_id": None,
            "code_index": None,
            "thought": thought,
            "plan": plan,
            "choice": choice,
            "reason": reason,
            "cooperation_levels": cooperation_levels,
        }

    if not p or p.status != "active":
        return {"action": "pass", "target_id": None, "code_index": None,
                "thought": "", "plan": "", "choice": "", "reason": "",
                "cooperation_levels": {}}

    if not others:
        return {"action": "pass", "target_id": None, "code_index": None,
                "thought": thought, "plan": plan, "choice": choice, "reason": reason,
                "cooperation_levels": cooperation_levels}

    can_steal = not skills.block_steal(p.role_id)

    coop_candidates = [(tid, lev) for tid, lev in cooperation_levels.items() if lev >= 0.66]
    defect_candidates = [(tid, lev) for tid, lev in cooperation_levels.items() if lev <= 0.33]

    action = "pass"
    target_id = None

    if coop_candidates:
        best_coop = max(coop_candidates, key=lambda x: (x[1], session.get_trust(agent_id, x[0])))
        action = "cooperate"
        target_id = best_coop[0]
    elif defect_candidates and can_steal:
        worst_defect = min(defect_candidates, key=lambda x: (session.get_trust(agent_id, x[0]), -x[1]))
        action = "steal"
        target_id = worst_defect[0]
    else:
        action, target_id = compute_action_utility(session, agent_id)
        if action in ("cooperate", "steal") and not others:
            action = "pass"
            target_id = None

    if action == "steal" and skills.block_steal(p.role_id):
        if coop_candidates:
            action = "cooperate"
            target_id = max(coop_candidates, key=lambda x: session.get_trust(agent_id, x[0]))[0]
        elif others:
            action = "cooperate"
            target_id = max(others, key=lambda o: session.get_trust(agent_id, o.agent_id)).agent_id
        else:
            action = "pass"
            target_id = None

    thought, plan, choice, reason = _build_intent_text(
        action, target_id, agent_id,
        agent_names=agent_names,
        last_messages=last_messages,
        agents_root=agents_root,
        cooperation_levels_per_target=cooperation_levels,
    )

    return {
        "action": action,
        "target_id": target_id,
        "code_index": None,
        "thought": thought,
        "plan": plan,
        "choice": choice,
        "reason": reason,
        "cooperation_levels": cooperation_levels,
    }
