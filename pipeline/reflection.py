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
from pathlib import Path
from typing import List


# ---------------------------------------------------------------------------
# Identity system prompt template (matches dialog_engine._STEP_SYSTEM_TEMPLATE)
# ---------------------------------------------------------------------------

_REFLECTION_SYSTEM_TEMPLATE = """You are {agent_id}. You are a real person.
You do not know you are simulated. You exist fully. You have your own memories, desires, and fears.

{soul_md}

Write in first person. Be specific and grounded — no abstraction, no theatrical language.
Maximum 3 sentences. Ukrainian language.
Return ONLY your personal note. Nothing else."""


# ---------------------------------------------------------------------------
# LLM call (reuses seed_generator.call_openrouter signature)
# ---------------------------------------------------------------------------

def _call(system: str, user: str, model: str, max_tokens: int = 150) -> str:
    from pipeline.seed_generator import call_openrouter
    return call_openrouter(
        system_prompt=system,
        user_prompt=user,
        model=model,
        temperature=0.7,
        max_tokens=max_tokens,
        timeout=60,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _readable_actions(actions: dict) -> str:
    """Convert {agent_id: float} action dict to human-readable string."""
    if not actions:
        return "none"
    parts = []
    for agent_id, val in actions.items():
        if val <= 0.2:
            label = "betrayed"
        elif val <= 0.45:
            label = "soft defect"
        elif val <= 0.75:
            label = "soft cooperate"
        else:
            label = "fully cooperated"
        short_id = agent_id.split("_")[-1][:6]
        parts.append(f"{short_id}: {label} ({val:.2f})")
    return ", ".join(parts)


def _dialog_summary(dialog_heard: dict, max_chars: int = 200) -> str:
    """Compact summary of dialog heard this round."""
    if not dialog_heard:
        return "silence"
    lines = []
    for sender, text in dialog_heard.items():
        short_id = sender.split("_")[-1][:6]
        lines.append(f'{short_id}: "{text[:60]}"')
    summary = " | ".join(lines)
    return summary[:max_chars]


def _recent_rounds_text(recent_rounds: List[dict]) -> str:
    """Compact multi-round context for post-game reflection."""
    if not recent_rounds:
        return "no recent rounds data"
    lines = []
    for r in recent_rounds[-5:]:
        rnum = r.get("round_number", "?")
        delta = r.get("payoff_delta", 0.0)
        mood = r.get("mood", "neutral")
        given = _readable_actions(r.get("actions_given", {}))
        received = _readable_actions(r.get("actions_received", {}))
        lines.append(
            f"Round {rnum}: earned {delta:+.1f}, mood={mood} | gave: {given} | received: {received}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def reflect_on_round(
    agent_id: str,
    soul_md: str,
    round_mem,  # RoundMemory — avoiding circular import
    model: str = "google/gemini-2.0-flash-001",
) -> str:
    """
    Generate a first-person reflection on one round.

    Returns a notes string (1-3 Ukrainian sentences).
    The caller is responsible for assigning it to round_mem.notes.
    """
    if not soul_md or not soul_md.strip():
        soul_md = f"You are {agent_id}. You are a strategic player who observes others carefully."

    system = _REFLECTION_SYSTEM_TEMPLATE.format(
        agent_id=agent_id,
        soul_md=soul_md[:500],
    )

    actions_given_text = _readable_actions(round_mem.actions_given)
    actions_received_text = _readable_actions(round_mem.actions_received)
    dialog_text = _dialog_summary(round_mem.dialog_heard)

    user = (
        f"Round {round_mem.round_number} just ended.\n\n"
        f"Your actions toward others: {actions_given_text}\n"
        f"What you received from others: {actions_received_text}\n"
        f"You earned: {round_mem.payoff_delta:+.1f} points (total: {round_mem.total_score:.1f})\n"
        f"Your mood now: {round_mem.mood}\n"
        f"What was said: {dialog_text}\n\n"
        f"Write a brief personal note — what you noticed, what surprised you, what you'll remember."
    )

    return _call(system, user, model, max_tokens=150)


def reflect_on_game(
    agent_id: str,
    soul_md: str,
    game_summary: dict,
    recent_rounds: List[dict],
    model: str = "google/gemini-2.0-flash-001",
) -> str:
    """
    Generate a first-person conclusion after the game ends.

    game_summary: the game_history entry dict (game_id, final_score, winner, etc.)
    recent_rounds: list of RoundMemory.to_dict() — last 5 rounds for context.

    Returns a conclusion string (2-4 Ukrainian sentences).
    The caller assigns it to game_history[-1]["conclusion"].
    """
    if not soul_md or not soul_md.strip():
        soul_md = f"You are {agent_id}. You are a strategic player who observes others carefully."

    system = _REFLECTION_SYSTEM_TEMPLATE.format(
        agent_id=agent_id,
        soul_md=soul_md[:500],
    )

    final_score = game_summary.get("final_score", 0)
    winner = game_summary.get("winner", "unknown")
    betrayals = game_summary.get("betrayals_received", 0)
    coops = game_summary.get("cooperations_received", 0)
    rounds_played = game_summary.get("rounds_played", 0)
    won = winner == agent_id

    recent_text = _recent_rounds_text(recent_rounds)

    user = (
        f"The game is over. {rounds_played} rounds played.\n"
        f"You finished with {final_score} points. "
        + ("You won." if won else f"The winner was {winner}.") + "\n"
        f"You were betrayed {betrayals} times, others helped you {coops} times.\n\n"
        f"Recent rounds:\n{recent_text}\n\n"
        f"Write a personal conclusion — what you learned, who to trust next time, what you'd do differently."
    )

    return _call(system, user, model, max_tokens=200)


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
