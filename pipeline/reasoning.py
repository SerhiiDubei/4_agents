"""
reasoning.py

Pre-decision LLM reasoning for Island agents.

Called after dialog and before choose_action() each round.
The agent thinks through who to trust, what happened last round,
and explicitly decides a cooperation level toward each other agent.

Returns a ReasoningResult with:
  - thought: free-text Ukrainian narrative (shown in logs)
  - intents: {agent_id: float} — explicit per-target action values (0.0/0.33/0.66/1.0)

The intents are used directly as decisions in game_engine.py,
with CORE math as fallback only when LLM fails.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class ReasoningResult:
    thought: str
    # Legacy: agent_id -> float (cooperation). Extended: agent_id -> {dim_id: float}
    intents: Dict[str, Union[float, Dict[str, float]]] = field(default_factory=dict)
    # New: structured social actions list [{target, type, value, visibility}, ...]
    # Populated when LLM returns new "actions" format; empty when using legacy intents
    social_actions: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {"thought": self.thought, "intents": self.intents}
        if self.social_actions:
            d["social_actions"] = self.social_actions
        return d

    @classmethod
    def empty(cls, thought: str = "") -> "ReasoningResult":
        return cls(thought=thought, intents={})


# ---------------------------------------------------------------------------
# JSON schema for structured output
# ---------------------------------------------------------------------------

# Legacy schema: intents as agent_id -> float (kept for fallback parsing)
_INTENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "intents": {
            "type": "object",
            "additionalProperties": True,
        },
    },
    "required": ["thought", "intents"],
    "additionalProperties": False,
}

# New schema: explicit social actions list
# LLM declares WHO + WHAT + HOW MUCH + visibility
# intents kept as optional fallback field
_ACTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "target":     {"type": "string"},
                    "type":       {"type": "string",
                                   "enum": ["share_food","alliance","warn",
                                            "ignore","betray","reciprocate","deceive"]},
                    "value":      {"type": "number", "minimum": 0, "maximum": 2},
                    "visibility": {"type": "string", "enum": ["public","private"]},
                },
                "required": ["target", "type", "value", "visibility"],
            },
        },
        "intents": {
            "type": "object",
            "additionalProperties": True,
        },
    },
    "required": ["thought", "actions"],
    "additionalProperties": False,
}

# Action type -> cooperation float mapping (for backward compat with decision_engine)
_ACTION_TYPE_TO_COOP = {
    "share_food":  1.0,
    "alliance":    1.0,
    "reciprocate": 0.66,
    "ignore":      0.33,
    "warn":        0.33,
    "deceive":     0.33,
    "betray":      0.0,
}

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_REASONING_SYSTEM_TEMPLATE = """You are {display_name}. You are a real person at a private gathering.
You do not know you are simulated. You exist fully. You have your own memories, desires, and fears.

{soul_md}

You are about to decide what social actions to take toward people in the room.
Think in first person. Ukrainian language. Use the people's NAMES in your thoughts — not codes or IDs.

People in the room with you: {peers_named}

You have a social budget of {budget_pool} to distribute this round.
The total value of all your actions MUST NOT exceed {budget_pool}.
You MUST declare at least 1 action.

ACTION TYPES:
  share_food  — give resources, build trust (positive, costs budget)
  alliance    — form explicit bond (positive, costs budget)
  reciprocate — return a favor (positive, costs budget)
  warn        — signal distrust publicly or privately (negative, costs budget)
  deceive     — mislead about your intentions (negative, costs budget)
  betray      — openly work against them (negative, costs budget)
  ignore      — do nothing toward them (neutral, costs 0 budget)

VISIBILITY: "public" = everyone sees it. "private" = only that person sees it.

Return JSON with two fields:
  "thought" — your internal reasoning (2-4 sentences, first person, Ukrainian, use their NAMES)
  "actions" — list of actions. Each has: target (agent ID), type, value (0.0–{budget_pool}), visibility

Example (if you are Кир with budget 1.2, others are Надя agent_511a6f9e, Рекс agent_synth_c, Льов agent_synth_d):
{{
  "thought": "Надя зрадила мене минулого разу, але Льов тримається чесно. Підтримаю Льова, а Наді дам зрозуміти що я пам'ятаю...",
  "actions": [
    {{"target": "agent_synth_d", "type": "share_food",  "value": 0.8, "visibility": "private"}},
    {{"target": "agent_511a6f9e","type": "warn",        "value": 0.3, "visibility": "public"}},
    {{"target": "agent_synth_c", "type": "ignore",      "value": 0.0, "visibility": "public"}}
  ]
}}

Your "thought" must be a natural internal monologue. NO numbers, NO "0.66", NO technical terms. Use only names and feelings.
The sum of all action values must be ≤ {budget_pool}."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dn(agent_id: str, names: dict) -> str:
    """Return display name for agent_id, fallback to short ID."""
    return names.get(agent_id) or agent_id.split("_")[-1][:8]


from pipeline.utils import _cooperation_val


def _format_received(actions_received: dict, names: dict = None) -> str:
    names = names or {}
    if not actions_received:
        return ""
    parts = []
    for aid, val in actions_received.items():
        v = _cooperation_val(val)
        name = _dn(aid, names)
        if v <= 0.15:
            label = "зрадив тебе (0.0)"
        elif v <= 0.45:
            label = f"м'яко зрадив ({v:.2f})"
        elif v <= 0.75:
            label = f"частково кооперував ({v:.2f})"
        else:
            label = f"повністю кооперував ({v:.2f})"
        parts.append(f"  {name}: {label}")
    return "\n".join(parts)


def _format_given(actions_given: dict, names: dict = None) -> str:
    names = names or {}
    if not actions_given:
        return ""
    parts = []
    for aid, val in actions_given.items():
        v = _cooperation_val(val)
        name = _dn(aid, names)
        if v <= 0.15:
            label = "ти зрадив (0.0)"
        elif v <= 0.45:
            label = f"ти м'яко зрадив ({v:.2f})"
        elif v <= 0.75:
            label = f"ти частково кооперував ({v:.2f})"
        else:
            label = f"ти повністю кооперував ({v:.2f})"
        parts.append(f"  {name}: {label}")
    return "\n".join(parts)


def _format_dialog(dialog_public: dict, dialog_dm: dict, names: dict = None) -> str:
    """Format dialog with clear separation between public and DM messages."""
    names = names or {}
    lines = []
    if dialog_public:
        lines.append("Публічно сказали:")
        for sender, text in list(dialog_public.items())[:4]:
            name = _dn(sender, names)
            lines.append(f'  {name}: "{text[:70]}"')
    if dialog_dm:
        lines.append("Приватно тобі написали (DM):")
        for sender, text in list(dialog_dm.items())[:3]:
            name = _dn(sender, names)
            lines.append(f'  {name} [DM]: "{text[:70]}"')
    return "\n".join(lines)


def _format_trust(trust_scores: dict, names: dict = None) -> str:
    names = names or {}
    if not trust_scores:
        return ""
    parts = []
    for aid, val in sorted(trust_scores.items(), key=lambda x: x[1]):
        name = _dn(aid, names)
        if val < 0.3:
            label = "не довіряєш"
        elif val < 0.5:
            label = "насторожено"
        elif val < 0.7:
            label = "нейтрально"
        else:
            label = "довіряєш"
        parts.append(f"  {name}: {val:.2f} ({label})")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def _call_structured(system: str, user: str, model: str, budget_pool: float = 1.0) -> ReasoningResult:
    # Використовуємо unified клієнт з retry замість голого call_openrouter
    from pipeline.llm_client import call_llm
    raw = call_llm(
        system=system,
        user=user,
        model=model,
        temperature=0.75,
        max_tokens=400,
        timeout=45,
        json_schema=_ACTIONS_SCHEMA,
        retries=3,
        retry_delay=2.0,
        label="reasoning",
    )
    try:
        parsed = json.loads(raw)
        thought = str(parsed.get("thought", "")).strip()

        # ── NEW FORMAT: actions[] ─────────────────────────────────
        raw_actions = parsed.get("actions")
        if raw_actions and isinstance(raw_actions, list):
            social_actions = []
            intents: Dict[str, Union[float, Dict[str, float]]] = {}
            valid_types = set(_ACTION_TYPE_TO_COOP.keys())

            for item in raw_actions:
                if not isinstance(item, dict):
                    continue
                target = str(item.get("target", "")).strip()
                atype  = str(item.get("type", "ignore")).strip()
                value  = float(item.get("value", 0.0))
                vis    = str(item.get("visibility", "public")).strip()

                if not target:
                    continue
                if atype not in valid_types:
                    atype = "ignore"
                if vis not in ("public", "private"):
                    vis = "public"
                value = max(0.0, min(value, budget_pool))

                social_actions.append({
                    "target": target, "type": atype,
                    "value": round(value, 3), "visibility": vis,
                })
                # Backward-compat intents: map action type → cooperation float
                intents[target] = _ACTION_TYPE_TO_COOP.get(atype, 0.5)

            return ReasoningResult(
                thought=thought,
                intents=intents,
                social_actions=social_actions,
            )

        # ── LEGACY FALLBACK: intents{} ────────────────────────────
        raw_intents = parsed.get("intents", {})
        _COOP_LEVELS = [0.0, 0.33, 0.66, 1.0]

        def snap_val(v) -> float:
            try:
                f = float(v)
                return min(_COOP_LEVELS, key=lambda a: abs(a - f))
            except (TypeError, ValueError):
                return 0.5

        intents = {}
        for agent_id, val in raw_intents.items():
            try:
                if isinstance(val, (int, float)):
                    intents[agent_id] = snap_val(val)
                elif isinstance(val, dict):
                    dim_vals = {k: snap_val(v) for k, v in val.items()}
                    intents[agent_id] = dim_vals if dim_vals else 0.5
            except (TypeError, ValueError):
                pass

        return ReasoningResult(thought=thought, intents=intents, social_actions=[])

    except (json.JSONDecodeError, KeyError, TypeError):
        return ReasoningResult.empty(thought=raw[:300] if raw else "")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_reasoning(
    agent_id: str,
    soul_md: str,
    round_number: int,
    total_rounds: int,
    peer_ids: List[str],
    last_round_summary: Optional[dict],
    dialog_heard: dict,
    trust_scores: dict,
    last_reflection: str = "",
    last_conclusion: str = "",
    memory_narrative: str = "",
    bio: str = "",
    model: str = "google/gemini-2.0-flash-001",
    agent_names: Optional[dict] = None,
    story_context: str = "",
    situation_text: str = "",
    situation_reflection: str = "",
    round_event_text: str = "",
    event_participants: Optional[List[str]] = None,
    budget_pool: float = 1.0,   # current social budget (from SocialState)
) -> ReasoningResult:
    """
    Generate structured per-target reasoning for this round.

    peer_ids: list of other agent IDs to decide toward (required for schema).
    dialog_heard: raw dict from game_engine — may mix public and DM messages.
                  DM messages are identified by keys starting with 'dm:'.
    last_reflection: agent's own note from the previous round (from RoundMemory.notes).
    last_conclusion: agent's post-game conclusion from last game (from memory.game_history).
    agent_names: {agent_id: display_name} — used in prompts so LLM uses real names.

    Returns ReasoningResult with thought + per-target intents.
    """
    names = agent_names or {}

    if not soul_md or not soul_md.strip():
        soul_md = f"You are {_dn(agent_id, names)}. You are strategic and observant."

    display_name = _dn(agent_id, names)

    # Build peers list with names + ID mapping so LLM knows the connection
    peers_named_parts = []
    for pid in peer_ids:
        pname = names.get(pid, "")
        if pname:
            peers_named_parts.append(f"{pname} (id: {pid})")
        else:
            peers_named_parts.append(pid)
    peers_named = ", ".join(peers_named_parts) if peers_named_parts else "(нікого)"

    system = _REASONING_SYSTEM_TEMPLATE.format(
        display_name=display_name,
        soul_md=soul_md[:900],
        peers_named=peers_named,
        budget_pool=round(budget_pool, 2),
    )

    rounds_left = total_rounds - round_number

    # Separate public vs DM from dialog_heard
    # Keys prefixed with "dm:" are DM messages, rest are public
    dialog_public = {}
    dialog_dm = {}
    for key, text in dialog_heard.items():
        if key.startswith("dm:"):
            real_sender = key[3:]
            dialog_dm[real_sender] = text
        else:
            dialog_public[key] = text

    # Format context sections
    received_text = ""
    given_text = ""
    if last_round_summary:
        received_text = _format_received(last_round_summary.get("received", {}), names)
        given_text = _format_given(last_round_summary.get("given", {}), names)

    dialog_text = _format_dialog(dialog_public, dialog_dm, names)
    trust_text = _format_trust(trust_scores, names)

    # Build peer list for prompt (names only for readability)
    peers_display = ", ".join(_dn(pid, names) for pid in peer_ids) if peer_ids else "(нікого)"

    user_parts = [
        f"Раунд {round_number}/{total_rounds}. Залишилось раундів: {rounds_left}.",
        f"Твої співрозмовники: {peers_display}",
    ]

    if story_context:
        user_parts.append(f"\nКонтекст історії: {story_context}")
    if round_event_text:
        user_parts.append(f"\nПодія цього акту: {round_event_text}")
    if event_participants and names:
        part_names = ", ".join(_dn(pid, names) for pid in event_participants)
        user_parts.append(f"\nУ цій події ти приймаєш рішення щодо: {part_names}. Решта — менш критичні в цей момент.")
    if situation_text:
        sit_short = situation_text[:350] + ("..." if len(situation_text) > 350 else "")
        user_parts.append(f"\nСитуація: {sit_short}")
    if situation_reflection and situation_reflection.strip():
        user_parts.append(f"\nТвоя реакція на ситуацію: {situation_reflection.strip()[:250]}")
    if bio and bio.strip():
        user_parts.append(f"\nТвоя біографія (коротко): {bio.strip()[:500]}")

    if received_text:
        user_parts.append(f"\nМинулий раунд — що зробили з тобою:\n{received_text}")
    if given_text:
        user_parts.append(f"\nМинулий раунд — що зробив ти:\n{given_text}")
    if trust_text:
        user_parts.append(f"\nПоточний рівень довіри:\n{trust_text}")
    if dialog_text:
        user_parts.append(f"\nЩо відбулось в діалозі:\n{dialog_text}")
    if memory_narrative and memory_narrative.strip():
        user_parts.append(f"\nТвоя пам'ять (підсумок): {memory_narrative.strip()}")
    else:
        if last_reflection:
            user_parts.append(f'\nТвоя власна нотатка з минулого раунду: "{last_reflection}"')
        if last_conclusion:
            user_parts.append(f'\nТвій висновок з минулої гри: "{last_conclusion[:350]}"')

    user_parts.append(
        f"\nТепер вирішуй: яке значення (0.0 / 0.33 / 0.66 / 1.0) ти даси кожному з {peers_display}?\n"
        "Поясни свою логіку в 'thought' (використовуй їхні ІМЕНА), "
        "потім заповни 'intents' точними agent ID як ключами і числами як значеннями."
    )

    user = "\n".join(user_parts)

    return _call_structured(system, user, model, budget_pool=budget_pool)
