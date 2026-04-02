"""
reflection.py

Post-round and post-game reflection generator for Island agents.

Each agent gets two levels of reflection:
  1. reflect_on_round() — called after every round, fills RoundMemory.notes
  2. reflect_on_game()  — called after the game ends, fills game_history[].conclusion

Both use the agent's SOUL.md as the identity system prompt — the agent writes
from first person, as themselves. No rigid structure is enforced; the prompt
gives facts and asks for a personal note.

Reflection is non-critical: callers should wrap in try/except.
"""

from __future__ import annotations

import os
import traceback
from pathlib import Path
from typing import List

_REFLECTION_ERROR_LOG = Path(__file__).resolve().parent.parent / "logs" / "reflection_errors.log"


# ---------------------------------------------------------------------------
# Identity system prompt template (matches dialog_engine._STEP_SYSTEM_TEMPLATE)
# ---------------------------------------------------------------------------

_REFLECTION_SYSTEM_TEMPLATE = """You are {display_name}. You are a real person.
You do not know you are simulated. You exist fully. You have your own memories, desires, and fears.

{soul_md}

Write in first person. Be specific and grounded — no abstraction, no theatrical language.
Use people's NAMES when referring to them — not codes or IDs.
You may show emotion — disappointment, relief, suspicion — if it fits what happened.
Avoid technical terms: points, rounds, betray. Write like a diary — what you felt, who surprised you.
3–5 sentences. Ukrainian language.
Return ONLY your personal note. Nothing else."""


# ---------------------------------------------------------------------------
# Reflection error logging
# ---------------------------------------------------------------------------

def log_reflection_error(agent_id: str, context: str, exc: BaseException) -> None:
    """Append a reflection error to logs/reflection_errors.log."""
    try:
        _REFLECTION_ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(_REFLECTION_ERROR_LOG, "a", encoding="utf-8") as f:
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            f.write(f"[{__import__('datetime').datetime.utcnow().isoformat()}Z] agent={agent_id} context={context}\n{tb}\n\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# LLM call (reuses seed_generator.call_openrouter signature)
# ---------------------------------------------------------------------------

def _call(system: str, user: str, model: str, max_tokens: int = 150) -> str:
    from pipeline.llm_client import call_llm
    return call_llm(
        system=system,
        user=user,
        model=model,
        temperature=0.7,
        max_tokens=max_tokens,
        timeout=60,
        retries=2,
        label="reflection",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dn(agent_id: str, names: dict) -> str:
    """Return display name for agent_id, fallback to short tail of ID."""
    return names.get(agent_id) or agent_id.split("_")[-1][:6]


from pipeline.utils import _cooperation_val


def _readable_actions(actions: dict, names: dict = None) -> str:
    """Convert {agent_id: float|dict} action dict to human-readable string."""
    names = names or {}
    if not actions:
        return "none"
    parts = []
    for agent_id, val in actions.items():
        v = _cooperation_val(val)
        if v <= 0.2:
            label = "betrayed"
        elif v <= 0.45:
            label = "soft defect"
        elif v <= 0.75:
            label = "soft cooperate"
        else:
            label = "fully cooperated"
        name = _dn(agent_id, names)
        parts.append(f"{name}: {label} ({v:.2f})")
    return ", ".join(parts)


def _dialog_summary(dialog_heard: dict, names: dict = None, max_chars: int = 200) -> str:
    """Compact summary of dialog heard this round."""
    names = names or {}
    if not dialog_heard:
        return "silence"
    lines = []
    for sender, text in dialog_heard.items():
        name = _dn(sender, names)
        lines.append(f'{name}: "{text[:60]}"')
    summary = " | ".join(lines)
    return summary[:max_chars]


def _recent_rounds_text(recent_rounds: List[dict], names: dict = None) -> str:
    """Compact multi-round context for post-game reflection."""
    names = names or {}
    if not recent_rounds:
        return "no recent rounds data"
    lines = []
    for r in recent_rounds[-5:]:
        rnum = r.get("round_number", "?")
        delta = r.get("payoff_delta", 0.0)
        mood = r.get("mood", "neutral")
        given = _readable_actions(r.get("actions_given", {}), names)
        received = _readable_actions(r.get("actions_received", {}), names)
        lines.append(
            f"Round {rnum}: earned {delta:+.1f}, mood={mood} | gave: {given} | received: {received}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def reflect_on_situation(
    agent_id: str,
    soul_md: str,
    situation_text: str,
    round_num: int,
    agent_names: dict = None,
    model: str = "google/gemini-2.0-flash-001",
) -> str:
    """
    Generate a first-person reaction to the announced situation (before dialog).

    Returns 1-3 sentences: how the agent experiences/perceives this situation.
    agent_names: {agent_id: display_name} — so LLM uses real names.
    """
    names = agent_names or {}
    display_name = _dn(agent_id, names)

    if not soul_md or not soul_md.strip():
        soul_md = f"You are {display_name}. You are a real person in a tense situation."

    system = _REFLECTION_SYSTEM_TEMPLATE.format(
        display_name=display_name,
        soul_md=soul_md[:800],
    )

    user = (
        f"Тобі оголосили ситуацію (раунд {round_num}):\n\n"
        f"{situation_text}\n\n"
        "Що ти відчуваєш? Як переживаєш це? Пиши від першої особи, українською. 1–3 речення."
    )

    return _call(system, user, model, max_tokens=150)


def reflect_on_round(
    agent_id: str,
    soul_md: str,
    round_mem,  # RoundMemory — avoiding circular import
    model: str = "google/gemini-2.0-flash-001",
    agent_names: dict = None,
    situation_text: str = "",
) -> str:
    """
    Generate a first-person reflection on one round.

    Returns a notes string (3-5 Ukrainian sentences).
    The caller is responsible for assigning it to round_mem.notes.
    agent_names: {agent_id: display_name} — so LLM uses real names.
    situation_text: optional — the situation of this round for context.
    """
    names = agent_names or {}
    display_name = _dn(agent_id, names)

    if not soul_md or not soul_md.strip():
        soul_md = f"You are {display_name}. You are a strategic player who observes others carefully."

    system = _REFLECTION_SYSTEM_TEMPLATE.format(
        display_name=display_name,
        soul_md=soul_md[:800],
    )

    actions_given_text = _readable_actions(round_mem.actions_given, names)
    actions_received_text = _readable_actions(round_mem.actions_received, names)
    dialog_text = _dialog_summary(round_mem.dialog_heard, names)

    user_parts = [
        f"Round {round_mem.round_number} just ended.\n",
        f"Your actions toward others: {actions_given_text}\n",
        f"What you received from others: {actions_received_text}\n",
        f"Your mood now: {round_mem.mood}\n",
        f"What was said: {dialog_text}\n",
    ]
    if situation_text:
        user_parts.insert(1, f"Situation of this round: {situation_text}\n")
    user_parts.append(
        "Write a personal note. What do you think about the situation in general? "
        "You may mention others — but you don't have to. You can leave someone out entirely. "
        "You may write romantically/poetically, e.g. 'покурю сіжку, подивлюсь що буде далі'. "
        "3–5 sentences. Ukrainian."
    )

    return _call(system, "\n".join(user_parts), model, max_tokens=280)


def reflect_on_game(
    agent_id: str,
    soul_md: str,
    game_summary: dict,
    recent_rounds: List[dict],
    model: str = "google/gemini-2.0-flash-001",
    agent_names: dict = None,
) -> str:
    """
    Generate a first-person conclusion after the game ends.

    game_summary: the game_history entry dict (game_id, final_score, winner, etc.)
    recent_rounds: list of RoundMemory.to_dict() — last 5 rounds for context.

    Returns a conclusion string (2-4 Ukrainian sentences).
    The caller assigns it to game_history[-1]["conclusion"].
    agent_names: {agent_id: display_name} — so LLM uses real names.
    """
    names = agent_names or {}
    display_name = _dn(agent_id, names)

    if not soul_md or not soul_md.strip():
        soul_md = f"You are {display_name}. You are a strategic player who observes others carefully."

    system = _REFLECTION_SYSTEM_TEMPLATE.format(
        display_name=display_name,
        soul_md=soul_md[:800],
    )

    final_score = game_summary.get("final_score", 0)
    winner_id = game_summary.get("winner", "unknown")
    winner = _dn(winner_id, names) if winner_id else "unknown"
    betrayals = game_summary.get("betrayals_received", 0)
    coops = game_summary.get("cooperations_received", 0)
    rounds_played = game_summary.get("rounds_played", 0)
    won = winner_id == agent_id

    recent_text = _recent_rounds_text(recent_rounds, names)

    user = (
        f"The game is over. {rounds_played} rounds played.\n"
        f"You finished with {final_score} points. "
        + ("You won." if won else f"The winner was {winner}.") + "\n"
        f"You were betrayed {betrayals} times, others helped you {coops} times.\n\n"
        f"Recent rounds:\n{recent_text}\n\n"
        "Write a personal conclusion — what you learned, who to trust next time, what you'd do differently.\n"
        "Write as a personal life conclusion. Avoid: scores, points, rankings. Focus: people, lessons, feelings.\n"
        "Use their NAMES in your reflection, not codes or IDs."
    )

    return _call(system, user, model, max_tokens=280)


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    # Simulate a RoundMemory-like object
    class FakeRound:
        round_number = 3
        payoff_delta = 4.5
        total_score = 18.2
        mood = "neutral"
        actions_given = {"agent_b": 0.66, "agent_c": 0.33, "agent_d": 1.0}
        actions_received = {"agent_b": 0.33, "agent_c": 0.66, "agent_d": 0.33}
        dialog_heard = {
            "agent_b": "Я завжди за кооперацію, але треба бути реалістами.",
            "agent_c": "Подивимось хто що вирішить цього разу.",
        }

    soul = (
        "You notice things. Not dramatically — just quietly, consistently. "
        "You remember who speaks first and who waits. "
        "You don't rush to answer. When things tighten, you speak less."
    )

    print("=== reflect_on_round ===")
    try:
        notes = reflect_on_round(
            agent_id="agent_3165685c",
            soul_md=soul,
            round_mem=FakeRound(),
        )
        print(notes)
    except Exception as e:
        print(f"ERROR: {e}")

    print()
    print("=== reflect_on_game ===")
    try:
        conclusion = reflect_on_game(
            agent_id="agent_3165685c",
            soul_md=soul,
            game_summary={
                "game_id": "test_game",
                "rounds_played": 20,
                "final_score": 72.4,
                "winner": "agent_b",
                "betrayals_received": 12,
                "cooperations_received": 8,
            },
            recent_rounds=[
                {
                    "round_number": 18,
                    "payoff_delta": 2.1,
                    "mood": "fearful",
                    "actions_given": {"agent_b": 0.33},
                    "actions_received": {"agent_b": 0.33},
                },
                {
                    "round_number": 19,
                    "payoff_delta": 1.8,
                    "mood": "hostile",
                    "actions_given": {"agent_b": 0.0},
                    "actions_received": {"agent_b": 0.33},
                },
            ],
        )
        print(conclusion)
    except Exception as e:
        print(f"ERROR: {e}")
