"""
TIME WARS skills: load roles, get skills by role/trigger, apply effects.
Triggers: BEFORE_STEAL_ROLL, ON_STEAL_FAIL, ON_STEAL_SUCCESS, ON_CODE_USE, ON_GAME_END, BLOCK.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from game_modes.time_wars.state import load_roles

_ROLES_PATH = Path(__file__).resolve().parent / "roles.json"


def get_roles(path: Optional[Path] = None) -> List[dict]:
    """Return list of role dicts from roles.json."""
    data = load_roles(path or _ROLES_PATH)
    return data.get("roles", [])


def get_skills_for_role(role_id: str, path: Optional[Path] = None) -> List[dict]:
    """Return list of skill dicts for the given role_id."""
    for role in get_roles(path):
        if role.get("id") == role_id:
            return role.get("skills", [])
    return []


def get_skills_by_trigger(trigger: str, path: Optional[Path] = None) -> List[tuple]:
    """Return list of (role_id, skill) for all skills with this trigger."""
    out = []
    for role in get_roles(path):
        rid = role.get("id", "")
        for skill in role.get("skills", []):
            if skill.get("trigger") == trigger:
                out.append((rid, skill))
    return out


def _skill_applies(skill: dict, context: dict) -> bool:
    """Check condition if present (e.g. steal_count == 0)."""
    cond = skill.get("condition")
    if not cond:
        return True
    # Simple condition: "steal_count == 0"
    if "steal_count" in cond and "==" in cond:
        try:
            want = int(cond.split("==")[1].strip())
            return context.get("steal_count", 0) == want
        except (ValueError, IndexError):
            pass
    return True


def apply_before_steal_roll(role_id: str, context: dict, path: Optional[Path] = None) -> dict:
    """
    Apply BEFORE_STEAL_ROLL skills (e.g. roll bonus).
    context: { "actor_id", "target_id", "base_roll", "trust", ... }
    Returns: { "roll_bonus": int, "block": bool } (add roll_bonus to d20).
    """
    result = {"roll_bonus": 0, "block": False}
    for skill in get_skills_for_role(role_id, path):
        if skill.get("trigger") != "BEFORE_STEAL_ROLL":
            continue
        if not _skill_applies(skill, context):
            continue
        eff = skill.get("effect", {})
        if "steal_roll_bonus" in eff:
            result["roll_bonus"] = result.get("roll_bonus", 0) + int(eff["steal_roll_bonus"])
    return result


def apply_on_steal_fail(role_id: str, context: dict, path: Optional[Path] = None) -> dict:
    """
    Apply ON_STEAL_FAIL skills (e.g. override penalty).
    context: { "actor_id", "default_penalty_seconds" }
    Returns: { "penalty_override": int | None } (if set, use instead of default).
    """
    result = {"penalty_override": None}
    for skill in get_skills_for_role(role_id, path):
        if skill.get("trigger") != "ON_STEAL_FAIL":
            continue
        if not _skill_applies(skill, context):
            continue
        eff = skill.get("effect", {})
        if "steal_fail_penalty_override" in eff:
            result["penalty_override"] = int(eff["steal_fail_penalty_override"])
    return result


def apply_on_steal_success(role_id: str, context: dict, path: Optional[Path] = None) -> dict:
    """
    Apply ON_STEAL_SUCCESS skills (e.g. extra time stolen).
    context: { "actor_id", "target_id", "base_actor_gain", "base_target_loss" }
    Returns: { "extra_time_stolen": int } (add to actor gain, subtract from target).
    """
    result = {"extra_time_stolen": 0}
    for skill in get_skills_for_role(role_id, path):
        if skill.get("trigger") != "ON_STEAL_SUCCESS":
            continue
        if not _skill_applies(skill, context):
            continue
        eff = skill.get("effect", {})
        if "extra_time_stolen" in eff:
            result["extra_time_stolen"] = result.get("extra_time_stolen", 0) + int(eff["extra_time_stolen"])
    return result


def apply_on_code_use(role_id: str, context: dict, path: Optional[Path] = None) -> dict:
    """
    Apply ON_CODE_USE skills (e.g. multiplier for Banker).
    context: { "actor_id", "base_seconds" }
    Returns: { "code_time_multiplier": float } (multiply base_seconds).
    """
    result = {"code_time_multiplier": 1.0}
    for skill in get_skills_for_role(role_id, path):
        if skill.get("trigger") != "ON_CODE_USE":
            continue
        if not _skill_applies(skill, context):
            continue
        eff = skill.get("effect", {})
        if "code_time_multiplier" in eff:
            result["code_time_multiplier"] = float(eff["code_time_multiplier"])
    return result


def apply_on_game_end(role_id: str, context: dict, path: Optional[Path] = None) -> dict:
    """
    Apply ON_GAME_END skills (e.g. bonus per coop if no steal).
    context: { "steal_count", "coop_count", ... }
    Returns: { "bonus_seconds": int } (add to player time at end).
    """
    result = {"bonus_seconds": 0}
    for skill in get_skills_for_role(role_id, path):
        if skill.get("trigger") != "ON_GAME_END":
            continue
        if not _skill_applies(skill, context):
            continue
        eff = skill.get("effect", {})
        if "bonus_per_coop_no_steal" in eff and context.get("steal_count", 0) == 0:
            bonus_per = int(eff["bonus_per_coop_no_steal"])
            result["bonus_seconds"] = result.get("bonus_seconds", 0) + context.get("coop_count", 0) * bonus_per
    return result


def apply_on_first_steal_attempt(role_id: str, context: dict, path: Optional[Path] = None) -> dict:
    """
    Apply ON_FIRST_STEAL_ATTEMPT (e.g. Peacekeeper extra penalty).
    context: { "actor_id", "is_first_steal" }
    Returns: { "extra_penalty_time": int } (subtract from actor on first steal attempt).
    """
    result = {"extra_penalty_time": 0}
    if not context.get("is_first_steal", False):
        return result
    for skill in get_skills_for_role(role_id, path):
        if skill.get("trigger") != "ON_FIRST_STEAL_ATTEMPT":
            continue
        eff = skill.get("effect", {})
        if "extra_penalty_time" in eff:
            result["extra_penalty_time"] = int(eff["extra_penalty_time"])
    return result


def block_steal(role_id: str, path: Optional[Path] = None) -> bool:
    """Return True if role blocks STEAL action (e.g. Banker)."""
    for skill in get_skills_for_role(role_id, path):
        if skill.get("trigger") == "BLOCK":
            eff = skill.get("effect", {})
            if eff.get("block_action") == "STEAL":
                return True
    return False
