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

    def to_dict(self) -> dict:
        return {"thought": self.thought, "intents": self.intents}

    @classmethod
    def empty(cls, thought: str = "") -> "ReasoningResult":
        return cls(thought=thought, intents={})


# ---------------------------------------------------------------------------
# JSON schema for structured output
# ---------------------------------------------------------------------------

# Schema allows intents to be agent_id -> number (cooperation) or agent_id -> {cooperation, support}
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

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_REASONING_SYSTEM_TEMPLATE = """You are {display_name}. You are a real person at a private gathering.
You do not know you are simulated. You exist fully. You have your own memories, desires, and fears.

{soul_md}

You are about to decide how much to cooperate with each person in the room.
Think in first person. Ukrainian language. Use the people's NAMES in your thoughts — not codes or IDs.

People in the room with you: {peers_named}

COOPERATION SCALE — you must assign exactly one value per person:
  0.0  = betray them completely (you give them nothing, take what you can)
  0.33 = soft defect (lean away, keep distance, minimal cooperation)
  0.66 = conditional cooperate (you give something, but hold back)
  1.0  = full trust (you cooperate fully, you expect the same back)

Return JSON with two fields:
  "thought" — your internal reasoning (2-4 sentences, first person, Ukrainian, use their NAMES)
  "intents" — one value per person: use their agent ID as key. Value is a number (0/0.33/0.66/1) for cooperation, or an object {{ "cooperation": number, "support": number }} for both axes.

Example (if you are Кир and others are Надя, Рекс, Льов):
{{
  "thought": "Надя зрадила мене минулого разу, тому не довіряю. З Льовом хочу спробувати співпрацю...",
  "intents": {{
    "agent_511a6f9e": 0.33,
    "agent_synth_c": 0.0,
    "agent_synth_d": 0.66
  }}
}}
Support scale (optional): 0 = passive, 1 = full support. If you omit support, it is inferred from your profile.

Your "thought" must be a natural internal monologue. NO numbers, NO "0.66", NO "soft-C", NO "coop/betray" terms. Use only names and feelings."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dn(agent_id: str, names: dict) -> str:
    """Return display name for agent_id, fallback to short ID."""
    return names.get(agent_id) or agent_id.split("_")[-1][:8]


def _cooperation_val(val) -> float:
    """Extract cooperation from legacy float or per-dim dict."""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, dict):
        return float(val.get("cooperation", 0.5))
    return 0.5


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

def _call_structured(system: str, user: str, model: str) -> ReasoningResult:
    from pipeline.seed_generator import call_openrouter
    raw = call_openrouter(
        system_prompt=system,
        user_prompt=user,
        model=model,
        temperature=0.75,
        max_tokens=300,
        timeout=45,
        json_schema=_INTENTS_SCHEMA,
    )
    try:
        parsed = json.loads(raw)
        thought = str(parsed.get("thought", "")).strip()
        raw_intents = parsed.get("intents", {})
        _ACTIONS = [0.0, 0.33, 0.66, 1.0]

        def snap_val(v) -> float:
            try:
                f = float(v)
                return min(_ACTIONS, key=lambda a: abs(a - f))
            except (TypeError, ValueError):
                return 0.5

        intents: Dict[str, Union[float, Dict[str, float]]] = {}
        for agent_id, val in raw_intents.items():
            try:
                if isinstance(val, (int, float)):
                    intents[agent_id] = snap_val(val)
                elif isinstance(val, dict):
                    dim_vals = {}
                    for dim_id, dval in val.items():
                        dim_vals[dim_id] = snap_val(dval)
                    if dim_vals:
                        intents[agent_id] = dim_vals
                    else:
                        intents[agent_id] = 0.5
                else:
                    pass
            except (TypeError, ValueError):
                pass
        return ReasoningResult(thought=thought, intents=intents)
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
    model: str = "google/gemini-2.0-flash-001",
    agent_names: Optional[dict] = None,
    story_context: str = "",
    situation_text: str = "",
    round_event_text: str = "",
    event_participants: Optional[List[str]] = None,
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

    if received_text:
        user_parts.append(f"\nМинулий раунд — що зробили з тобою:\n{received_text}")
    if given_text:
        user_parts.append(f"\nМинулий раунд — що зробив ти:\n{given_text}")
    if trust_text:
        user_parts.append(f"\nПоточний рівень довіри:\n{trust_text}")
    if dialog_text:
        user_parts.append(f"\nЩо відбулось в діалозі:\n{dialog_text}")
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

    return _call_structured(system, user, model)
