"""
TIME WARS agent integration: build context for LLM (time, role, skills, others, events, inventory).
Action choice: COOPERATE (with whom), STEAL (from whom), USE_CODE (which), PASS.
Thin layer: does not modify pipeline/dialog or pipeline/reasoning; only builds context and parses action.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from game_modes.time_wars.state import Session
from game_modes.time_wars import skills


def build_context(
    session: Session,
    agent_id: str,
    agent_name: str = "",
    last_events_count: int = 10,
) -> str:
    """
    Build a string context for the agent: own time, role, skills, others' times, last events, inventory.
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
        others.append(f"  {o.agent_id}: {o.time_remaining_sec}s ({o.role_id})")
    events_str = ""
    for ev in session.event_log[-last_events_count:]:
        et = ev.get("event_type", "")
        a = ev.get("actor_id", "")
        t = ev.get("target_id", "")
        d = ev.get("time_delta_seconds", 0)
        events_str += f"  [{et}] {a} -> {t} delta={d}\n"
    inv_str = ", ".join(str(c.get("seconds", 0)) + "s" for c in p.inventory) if p.inventory else "немає"
    return (
        f"Ти: {agent_name or agent_id}. Залишок часу: {p.time_remaining_sec} сек. Роль: {p.role_id}. Скіли: {', '.join(skill_names)}.\n"
        f"Інші гравці:\n" + "\n".join(others) + "\n"
        f"Останні події:\n{events_str}"
        f"Інвентар (коди): {inv_str}\n"
        f"Обери одну дію: COOPERATE <agent_id>, STEAL <agent_id>, USE_CODE <index>, або PASS."
    )


def parse_action(response: str, agent_id: str, session: Session) -> Dict[str, Any]:
    """
    Parse agent response into action dict.
    response: raw LLM or mock response.
    Returns {"action": "cooperate"|"steal"|"use_code"|"pass", "target_id": str|None, "code_index": int|None}.
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
    if "USE_CODE" in response:
        p = session.get_player(agent_id)
        if p and p.inventory:
            try:
                idx = int(response.split("USE_CODE")[-1].strip().split()[0])
                if 0 <= idx < len(p.inventory):
                    return {"action": "use_code", "target_id": None, "code_index": idx}
            except (ValueError, IndexError):
                pass
            return {"action": "use_code", "target_id": None, "code_index": 0}
    return {"action": "pass", "target_id": None, "code_index": None}


def get_agent_action_mock(
    session: Session,
    agent_id: str,
    rng: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Mock action for testing: random valid action (cooperate, steal, use_code, pass).
    Does not call LLM.
    """
    import random
    rng = rng or random
    p = session.get_player(agent_id)
    if not p or p.status != "active":
        return {"action": "pass", "target_id": None, "code_index": None}
    others = [o for o in session.active_players() if o.agent_id != agent_id]
    choices = ["pass"]
    if others:
        choices.extend(["cooperate", "steal"])
    if p.inventory:
        choices.append("use_code")
    action = rng.choice(choices)
    target_id = rng.choice(others).agent_id if others and action in ("cooperate", "steal") else None
    code_index = rng.randint(0, len(p.inventory) - 1) if action == "use_code" and p.inventory else None
    if action == "steal" and target_id and skills.block_steal(p.role_id):
        action = "pass"
        target_id = None
    return {"action": action, "target_id": target_id, "code_index": code_index}
