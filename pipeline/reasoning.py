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
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class ReasoningResult:
    thought: str
    intents: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"thought": self.thought, "intents": self.intents}

    @classmethod
    def empty(cls, thought: str = "") -> "ReasoningResult":
        return cls(thought=thought, intents={})


# ---------------------------------------------------------------------------
# JSON schema for structured output
# ---------------------------------------------------------------------------

_INTENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "intents": {
            "type": "object",
            "additionalProperties": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
            },
        },
    },
    "required": ["thought", "intents"],
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_REASONING_SYSTEM_TEMPLATE = """You are {agent_id}. You are a real person at a private gathering.
You do not know you are simulated. You exist fully. You have your own memories, desires, and fears.

{soul_md}

You are about to decide how much to cooperate with each person in the room.
Think in first person. Ukrainian language.

COOPERATION SCALE — you must assign exactly one value per person:
  0.0  = betray them completely (you give them nothing, take what you can)
  0.33 = soft defect (lean away, keep distance, minimal cooperation)
  0.66 = conditional cooperate (you give something, but hold back)
  1.0  = full trust (you cooperate fully, you expect the same back)

Return JSON with two fields:
  "thought" — your internal reasoning (2-4 sentences, first person, Ukrainian)
  "intents" — one value per person you'll decide toward: exact agent IDs as keys, number from scale as value

Example:
{{
  "thought": "511a6f9e зрадив мене минулого разу, тому не довіряю. З synth_d хочу спробувати співпрацю...",
  "intents": {{
    "agent_511a6f9e": 0.33,
    "agent_synth_c": 0.0,
    "agent_synth_d": 0.66
  }}
}}"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_received(actions_received: dict) -> str:
    if not actions_received:
        return ""
    parts = []
    for aid, val in actions_received.items():
        short = aid.split("_")[-1][:8]
        if val <= 0.15:
            label = "зрадив тебе (0.0)"
        elif val <= 0.45:
            label = f"м'яко зрадив ({val:.2f})"
        elif val <= 0.75:
            label = f"частково кооперував ({val:.2f})"
        else:
            label = f"повністю кооперував ({val:.2f})"
        parts.append(f"  {short}: {label}")
    return "\n".join(parts)


def _format_given(actions_given: dict) -> str:
    if not actions_given:
        return ""
    parts = []
    for aid, val in actions_given.items():
        short = aid.split("_")[-1][:8]
        if val <= 0.15:
            label = "ти зрадив (0.0)"
        elif val <= 0.45:
            label = f"ти м'яко зрадив ({val:.2f})"
        elif val <= 0.75:
            label = f"ти частково кооперував ({val:.2f})"
        else:
            label = f"ти повністю кооперував ({val:.2f})"
        parts.append(f"  {short}: {label}")
    return "\n".join(parts)


def _format_dialog(dialog_public: dict, dialog_dm: dict) -> str:
    """Format dialog with clear separation between public and DM messages."""
    lines = []
    if dialog_public:
        lines.append("Публічно сказали:")
        for sender, text in list(dialog_public.items())[:4]:
            short = sender.split("_")[-1][:8]
            lines.append(f'  {short}: "{text[:70]}"')
    if dialog_dm:
        lines.append("Приватно тобі написали (DM):")
        for sender, text in list(dialog_dm.items())[:3]:
            short = sender.split("_")[-1][:8]
            lines.append(f'  {short} [DM]: "{text[:70]}"')
    return "\n".join(lines)


def _format_trust(trust_scores: dict) -> str:
    if not trust_scores:
        return ""
    parts = []
    for aid, val in sorted(trust_scores.items(), key=lambda x: x[1]):
        short = aid.split("_")[-1][:8]
        if val < 0.3:
            label = "не довіряєш"
        elif val < 0.5:
            label = "насторожено"
        elif val < 0.7:
            label = "нейтрально"
        else:
            label = "довіряєш"
        parts.append(f"  {short}: {val:.2f} ({label})")
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
        # Snap to valid ACTIONS: 0.0, 0.33, 0.66, 1.0
        _ACTIONS = [0.0, 0.33, 0.66, 1.0]
        intents = {}
        for agent_id, val in raw_intents.items():
            try:
                f = float(val)
                snapped = min(_ACTIONS, key=lambda a: abs(a - f))
                intents[agent_id] = snapped
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
    model: str = "google/gemini-2.0-flash-001",
) -> ReasoningResult:
    """
    Generate structured per-target reasoning for this round.

    peer_ids: list of other agent IDs to decide toward (required for schema).
    dialog_heard: raw dict from game_engine — may mix public and DM messages.
                  DM messages are identified by keys starting with 'dm:'.
    last_reflection: agent's own note from the previous round (from RoundMemory.notes).

    Returns ReasoningResult with thought + per-target intents.
    """
    if not soul_md or not soul_md.strip():
        soul_md = f"You are {agent_id}. You are strategic and observant."

    system = _REASONING_SYSTEM_TEMPLATE.format(
        agent_id=agent_id,
        soul_md=soul_md[:600],
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
        received_text = _format_received(last_round_summary.get("received", {}))
        given_text = _format_given(last_round_summary.get("given", {}))

    dialog_text = _format_dialog(dialog_public, dialog_dm)
    trust_text = _format_trust(trust_scores)

    # Build peer list for prompt
    peers_line = ", ".join(peer_ids) if peer_ids else "(нікого)"

    user_parts = [
        f"Раунд {round_number}/{total_rounds}. Залишилось раундів: {rounds_left}.",
        f"Твої співрозмовники: {peers_line}",
    ]

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

    user_parts.append(
        f"\nТепер вирішуй: яке значення (0.0 / 0.33 / 0.66 / 1.0) ти даси кожному з {peers_line}?\n"
        "Поясни свою логіку в 'thought', потім заповни 'intents' точними значеннями для кожного."
    )

    user = "\n".join(user_parts)

    return _call_structured(system, user, model)
