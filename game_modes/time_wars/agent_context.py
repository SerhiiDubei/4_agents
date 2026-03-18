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
    Mock action for testing: random valid action with basic survival heuristic.
    - If time_sec < danger threshold → prefer use_code or steal over pass
    - Does not call LLM.
    """
    import random
    rng = rng or random
    p = session.get_player(agent_id)
    if not p or p.status != "active":
        return {"action": "pass", "target_id": None, "code_index": None}

    others = [o for o in session.active_players() if o.agent_id != agent_id]
    can_steal = not skills.block_steal(p.role_id)

    # Survival heuristic: when low on time, heavily prefer action over pass
    base_sec = session.base_seconds_per_player
    danger_threshold = max(200, base_sec // 4)
    in_danger = p.time_remaining_sec < danger_threshold

    if in_danger:
        # Priority: use code if have one, else steal (if allowed), else cooperate
        if p.inventory:
            action = "use_code"
            code_index = 0  # use first code in inventory
            target_id = None
            thought = "Критично мало часу — використовую код!"
            code_id = p.inventory[0].get("id", "код")
            plan = f"Використовую код {code_id} для виживання."
            choice = f"Код {code_id} (виживання)."
            reason = "Часу критично мало, потрібен негайний буст."
        elif can_steal and others:
            # Steal from the richest player
            target = max(others, key=lambda o: o.time_remaining_sec)
            action = "steal"
            target_id = target.agent_id
            code_index = None
            thought = "Критично — краду у найбагатшого."
            plan = f"Краду у {target_id} (є найбільше часу)."
            choice = f"Крадіжка у {target_id}."
            reason = "Остання можливість вижити."
        elif others:
            target = rng.choice(others)
            action = "cooperate"
            target_id = target.agent_id
            code_index = None
            thought = "Немає кодів та не можу красти — кооперую."
            plan = f"Кооперую з {target_id}."
            choice = f"Кооперація з {target_id}."
            reason = "Єдиний спосіб отримати час."
        else:
            action = "pass"
            target_id = None
            code_index = None
            thought = "Нічого не роблю."
            plan = "Пас."
            choice = "Пас."
            reason = "Немає варіантів."
    else:
        # Normal mode: role-specific weighted choices
        # Weights: [pass, cooperate, steal, use_code] — role shapes the mix
        role = p.role_id
        if role == "role_peacekeeper":
            # Peacekeeper: cooperative focus, rare steal (preserves ON_GAME_END bonus)
            w_pass, w_coop, w_steal, w_code = 1, 4, 1, 3
        elif role == "role_snake":
            # Snake: steal-leaning (lower than before to avoid extreme dominance)
            w_pass, w_coop, w_steal, w_code = 1, 2, 3, 2
        elif role == "role_gambler":
            # Gambler: moderate steal (high variance role — don't over-commit)
            w_pass, w_coop, w_steal, w_code = 1, 3, 2, 2
        elif role == "role_banker":
            # Banker: no steal → codes are the primary weapon (2x multiplier), then coop
            w_pass, w_coop, w_steal, w_code = 1, 2, 0, 4
        else:
            w_pass, w_coop, w_steal, w_code = 2, 2, 2, 1

        choices, weights = [], []
        choices.append("pass"); weights.append(w_pass)
        if others:
            choices.append("cooperate"); weights.append(w_coop)
            if can_steal:
                choices.append("steal"); weights.append(w_steal)
        if p.inventory:
            choices.append("use_code"); weights.append(w_code)

        action = rng.choices(choices, weights=weights, k=1)[0]
        target_id = rng.choice(others).agent_id if others and action in ("cooperate", "steal") else None
        code_index = rng.randint(0, len(p.inventory) - 1) if action == "use_code" and p.inventory else None
        if action == "steal" and target_id and not can_steal:
            action = "pass"
            target_id = None

        thought = plan = choice = reason = ""
        if action == "cooperate" and target_id:
            thought = "Хочу підсилити союзника."
            plan = f"Кооперую з {target_id}."
            choice = f"Кооперація з {target_id}."
            reason = "Взаємна вигода."
        elif action == "steal" and target_id:
            thought = "Ризикую забрати час."
            plan = f"Краду у {target_id}."
            choice = f"Крадіжка у {target_id}."
            reason = "Потрібен час; готовий до ризику штрафу."
        elif action == "use_code" and code_index is not None and p.inventory:
            code_id = p.inventory[code_index].get("id", "код") if code_index < len(p.inventory) else "код"
            thought = "Використаю код з інвентаря."
            plan = f"Використовую код {code_id}."
            choice = f"Код {code_id}."
            reason = "Потрібен буст часу."
        else:
            thought = "Нічого не роблю."
            plan = "Пас."
            choice = "Пас."
            reason = "Зберігаю опції."

    return {
        "action": action,
        "target_id": target_id,
        "code_index": code_index,
        "thought": thought,
        "plan": plan,
        "choice": choice,
        "reason": reason,
    }
