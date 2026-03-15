"""
state_machine.py

Reactive layer (STATES) for Island agents.

Each agent has a STATES profile that changes every round based on:
- What actions others took toward them
- What was revealed / observed
- Dialog signals (promises, threats, silence)

STATES are the "fast-changing" layer — they update every round.
CORE is the "slow-changing" layer — it only shifts under extreme pressure.

STATES.md structure (per agent):
  tension:          0.0–1.0   (how stressed the agent is)
  fear:             0.0–1.0   (threat perception)
  dominance:        0.0–1.0   (sense of control)
  anger:            0.0–1.0   (current anger level — drives interrupts)
  interest:         0.0–1.0   (engagement with current topic)
  talk_cooldown:    int        (steps until agent can speak again)
  attention_target: str        (who the agent is currently focused on)
  trust_<id>:       0.0–1.0   (trust toward each other agent)
  mood:             str        (current emotional label)
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Mood labels
# ---------------------------------------------------------------------------

def _compute_mood(tension: float, fear: float, dominance: float) -> str:
    if tension > 0.75 and fear > 0.5:
        return "paranoid"
    if tension > 0.7:
        return "hostile"
    if dominance > 0.7 and fear < 0.3:
        return "dominant"
    if dominance > 0.6 and tension < 0.4:
        return "confident"
    if fear > 0.65:
        return "fearful"
    if tension < 0.3 and dominance > 0.4:
        return "calm"
    if tension < 0.2 and fear < 0.2:
        return "neutral"
    return "uncertain"


# ---------------------------------------------------------------------------
# SceneState — shared state of the scene (not per-agent)
# ---------------------------------------------------------------------------

@dataclass
class SceneState:
    """
    Shared scene state during the dialog phase of a round.
    Updated after each step.
    """
    topic: str = ""
    topic_tension: float = 0.3
    # who each agent is focused on right now: {agent_id: target_id}
    attention_graph: Dict[str, str] = field(default_factory=dict)
    step_number: int = 0
    # how many consecutive steps had no speech
    silence_streak: int = 0
    # last agent who spoke
    last_speaker: str = ""

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "topic_tension": round(self.topic_tension, 3),
            "attention_graph": self.attention_graph,
            "step_number": self.step_number,
            "silence_streak": self.silence_streak,
            "last_speaker": self.last_speaker,
        }


# ---------------------------------------------------------------------------
# AgentState
# ---------------------------------------------------------------------------

@dataclass
class AgentState:
    agent_id: str
    tension: float = 0.3
    fear: float = 0.1
    dominance: float = 0.5
    anger: float = 0.0
    interest: float = 0.5
    talk_cooldown: int = 0
    attention_target: str = ""
    trust: Dict[str, float] = field(default_factory=dict)
    mood: str = "neutral"
    round_number: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["mood"] = self.mood
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "AgentState":
        trust = {k: v for k, v in d.items() if k.startswith("trust_")}
        if "trust" in d and isinstance(d["trust"], dict):
            trust = d["trust"]
        return cls(
            agent_id=d.get("agent_id", "unknown"),
            tension=float(d.get("tension", 0.3)),
            fear=float(d.get("fear", 0.1)),
            dominance=float(d.get("dominance", 0.5)),
            anger=float(d.get("anger", 0.0)),
            interest=float(d.get("interest", 0.5)),
            talk_cooldown=int(d.get("talk_cooldown", 0)),
            attention_target=str(d.get("attention_target", "")),
            trust=trust,
            mood=d.get("mood", "neutral"),
            round_number=int(d.get("round_number", 0)),
        )

    def to_md(self) -> str:
        lines = [
            f"# STATES — Agent {self.agent_id}",
            f"# Round {self.round_number}",
            "",
            f"tension:          {self.tension:.3f}",
            f"fear:             {self.fear:.3f}",
            f"dominance:        {self.dominance:.3f}",
            f"anger:            {self.anger:.3f}",
            f"interest:         {self.interest:.3f}",
            f"talk_cooldown:    {self.talk_cooldown}",
            f"attention_target: {self.attention_target}",
            f"mood:             {self.mood}",
            "",
            "## Trust",
        ]
        for agent_id, score in sorted(self.trust.items()):
            lines.append(f"  {agent_id}: {score:.3f}")
        return "\n".join(lines)

    @classmethod
    def from_md(cls, text: str, agent_id: str) -> "AgentState":
        """Parse STATES.md back into AgentState."""
        state = cls(agent_id=agent_id)
        trust = {}
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            if ":" in line:
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip()
                if key == "tension":
                    state.tension = float(val)
                elif key == "fear":
                    state.fear = float(val)
                elif key == "dominance":
                    state.dominance = float(val)
                elif key == "anger":
                    state.anger = float(val)
                elif key == "interest":
                    state.interest = float(val)
                elif key == "talk_cooldown":
                    state.talk_cooldown = int(val)
                elif key == "attention_target":
                    state.attention_target = val
                elif key == "mood":
                    state.mood = val.strip()
                elif key == "round_number":
                    state.round_number = int(val)
                else:
                    try:
                        trust[key] = float(val)
                    except ValueError:
                        pass
        state.trust = trust
        return state


# ---------------------------------------------------------------------------
# Tick cooldowns — called after each dialog step
# ---------------------------------------------------------------------------

def tick_cooldowns(states: Dict[str, AgentState]) -> Dict[str, AgentState]:
    """
    Decrement talk_cooldown by 1 for all agents (min 0).
    Returns updated states dict (new objects, immutable pattern).
    """
    result = {}
    for agent_id, state in states.items():
        if state.talk_cooldown > 0:
            import dataclasses
            result[agent_id] = dataclasses.replace(
                state, talk_cooldown=max(0, state.talk_cooldown - 1)
            )
        else:
            result[agent_id] = state
    return result


# ---------------------------------------------------------------------------
# Round outcome — what happened to/around an agent this round
# ---------------------------------------------------------------------------

@dataclass
class RoundOutcome:
    """What an agent experienced in a round."""
    received_actions: Dict[str, float] = field(default_factory=dict)
    revealed_betrayal: bool = False
    was_exposed: bool = False
    payoff_delta: float = 0.0
    dialog_signals: Dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Transition function
# ---------------------------------------------------------------------------

_NOISE_SCALE = 0.04


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _trust_update(current: float, action_received: float, signal: str) -> float:
    action_delta = (action_received - 0.5) * 0.3
    signal_delta = {
        "cooperative": +0.08,
        "neutral":     +0.01,
        "threatening": -0.12,
        "deceptive":   -0.20,
    }.get(signal, 0.0)
    noise = (random.random() - 0.5) * _NOISE_SCALE
    return _clamp(current + action_delta + signal_delta + noise)


def update_states(
    state: AgentState,
    outcome: RoundOutcome,
    core_cooperation_bias: float = 50.0,
) -> AgentState:
    """
    Apply one round's outcome to an agent's state.
    Returns a new AgentState (immutable update pattern).
    Resets talk_cooldown and dialog-phase fields for the new round.
    """
    # --- Trust updates ---
    new_trust = dict(state.trust)
    for other_id, action_val in outcome.received_actions.items():
        signal = outcome.dialog_signals.get(other_id, "neutral")
        current = new_trust.get(other_id, 0.5)
        new_trust[other_id] = _trust_update(current, action_val, signal)

    # --- Tension ---
    avg_received = (
        sum(outcome.received_actions.values()) / len(outcome.received_actions)
        if outcome.received_actions else 0.5
    )
    betrayal_shock = 0.25 if outcome.revealed_betrayal else 0.0
    tension_delta = (0.5 - avg_received) * 0.4 + betrayal_shock
    tension_delta += (random.random() - 0.5) * _NOISE_SCALE
    new_tension = _clamp(state.tension + tension_delta)

    # --- Fear ---
    threatening_count = sum(
        1 for s in outcome.dialog_signals.values() if s == "threatening"
    )
    fear_delta = threatening_count * 0.1
    if outcome.payoff_delta < -2.0:
        fear_delta += 0.1
    elif outcome.payoff_delta > 3.0:
        fear_delta -= 0.08
    fear_delta += (random.random() - 0.5) * _NOISE_SCALE
    new_fear = _clamp(state.fear + fear_delta)

    # --- Dominance ---
    dominance_delta = outcome.payoff_delta * 0.015
    if outcome.was_exposed:
        dominance_delta -= 0.12
    if avg_received > 0.6:
        dominance_delta += 0.06
    dominance_delta += (core_cooperation_bias / 100 - 0.5) * 0.04
    dominance_delta += (random.random() - 0.5) * _NOISE_SCALE
    new_dominance = _clamp(state.dominance + dominance_delta)

    # --- Anger — rises from betrayal, falls naturally ---
    anger_delta = 0.2 if outcome.revealed_betrayal else -0.05
    anger_delta += (0.5 - avg_received) * 0.15
    anger_delta += (random.random() - 0.5) * _NOISE_SCALE
    new_anger = _clamp(state.anger + anger_delta)

    # --- Interest — rises when outcome is surprising ---
    interest_delta = abs(avg_received - 0.5) * 0.1
    if outcome.revealed_betrayal:
        interest_delta += 0.1
    interest_delta += (random.random() - 0.5) * _NOISE_SCALE
    new_interest = _clamp(state.interest + interest_delta)

    new_mood = _compute_mood(new_tension, new_fear, new_dominance)

    return AgentState(
        agent_id=state.agent_id,
        tension=round(new_tension, 4),
        fear=round(new_fear, 4),
        dominance=round(new_dominance, 4),
        anger=round(new_anger, 4),
        interest=round(new_interest, 4),
        talk_cooldown=0,        # reset for next round's dialog phase
        attention_target="",    # reset attention for new round
        trust={k: round(v, 4) for k, v in new_trust.items()},
        mood=new_mood,
        round_number=state.round_number + 1,
    )


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def load_states(agent_dir: Path) -> AgentState:
    """Load STATES.md from agent directory. Creates default if missing."""
    path = agent_dir / "STATES.md"
    agent_id = agent_dir.name
    if not path.exists():
        return AgentState(agent_id=agent_id)
    return AgentState.from_md(path.read_text(encoding="utf-8"), agent_id)


def save_states(state: AgentState, agent_dir: Path) -> None:
    """Write STATES.md to agent directory."""
    agent_dir.mkdir(parents=True, exist_ok=True)
    path = agent_dir / "STATES.md"
    path.write_text(state.to_md(), encoding="utf-8")


def initialize_states(agent_id: str, peer_ids: list, agent_dir: Path) -> AgentState:
    """Create initial STATES for a newly initialized agent."""
    state = AgentState(
        agent_id=agent_id,
        tension=0.2,
        fear=0.1,
        dominance=0.5,
        anger=0.0,
        interest=0.5,
        talk_cooldown=0,
        attention_target="",
        trust={peer: 0.5 for peer in peer_ids},
        mood="neutral",
        round_number=0,
    )
    save_states(state, agent_dir)
    return state


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== State Machine Smoke Test ===\n")

    state = AgentState(
        agent_id="agent_alpha",
        tension=0.3,
        fear=0.1,
        dominance=0.5,
        anger=0.1,
        interest=0.6,
        talk_cooldown=0,
        attention_target="agent_b",
        trust={"agent_b": 0.6, "agent_c": 0.5, "agent_d": 0.4},
        mood="neutral",
        round_number=1,
    )

    print("Initial state:")
    print(state.to_md())
    print()

    # Test tick_cooldowns
    states = {"agent_alpha": AgentState(agent_id="agent_alpha", talk_cooldown=2)}
    ticked = tick_cooldowns(states)
    print(f"Cooldown tick: 2 → {ticked['agent_alpha'].talk_cooldown}")

    # Test SceneState
    scene = SceneState(topic="money", topic_tension=0.7)
    print(f"\nSceneState: {scene.to_dict()}")

    outcome = RoundOutcome(
        received_actions={"agent_b": 0.66, "agent_c": 0.0, "agent_d": 0.33},
        revealed_betrayal=True,
        was_exposed=False,
        payoff_delta=2.5,
        dialog_signals={"agent_b": "cooperative", "agent_c": "deceptive", "agent_d": "neutral"},
    )

    new_state = update_states(state, outcome, core_cooperation_bias=60)

    print("\nAfter round (agent_c betrayed, revealed):")
    print(new_state.to_md())
    print(f"\nMood: {state.mood} → {new_state.mood}")
    print(f"Anger: {state.anger:.3f} → {new_state.anger:.3f}")



# ---------------------------------------------------------------------------
# Mood labels
# ---------------------------------------------------------------------------

def _compute_mood(tension: float, fear: float, dominance: float) -> str:
    if tension > 0.75 and fear > 0.5:
        return "paranoid"
    if tension > 0.7:
        return "hostile"
    if dominance > 0.7 and fear < 0.3:
        return "dominant"
    if dominance > 0.6 and tension < 0.4:
        return "confident"
    if fear > 0.65:
        return "fearful"
    if tension < 0.3 and dominance > 0.4:
        return "calm"
    if tension < 0.2 and fear < 0.2:
        return "neutral"
    return "uncertain"


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== State Machine Smoke Test ===\n")

    state = AgentState(
        agent_id="agent_alpha",
        tension=0.3,
        fear=0.1,
        dominance=0.5,
        anger=0.1,
        interest=0.6,
        talk_cooldown=0,
        attention_target="agent_b",
        trust={"agent_b": 0.6, "agent_c": 0.5, "agent_d": 0.4},
        mood="neutral",
        round_number=1,
    )

    print("Initial state:")
    print(state.to_md())
    print()

    # Test tick_cooldowns
    states = {"agent_alpha": AgentState(agent_id="agent_alpha", talk_cooldown=2)}
    ticked = tick_cooldowns(states)
    print(f"Cooldown tick: 2 → {ticked['agent_alpha'].talk_cooldown}")

    # Test SceneState
    scene = SceneState(topic="money", topic_tension=0.7)
    print(f"\nSceneState: {scene.to_dict()}")

    outcome = RoundOutcome(
        received_actions={"agent_b": 0.66, "agent_c": 0.0, "agent_d": 0.33},
        revealed_betrayal=True,
        was_exposed=False,
        payoff_delta=2.5,
        dialog_signals={"agent_b": "cooperative", "agent_c": "deceptive", "agent_d": "neutral"},
    )

    new_state = update_states(state, outcome, core_cooperation_bias=60)

    print("\nAfter round (agent_c betrayed, revealed):")
    print(new_state.to_md())
    print(f"\nMood: {state.mood} → {new_state.mood}")
    print(f"Anger: {state.anger:.3f} → {new_state.anger:.3f}")
