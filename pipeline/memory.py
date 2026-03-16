"""
memory.py

Append-only memory log for Island agents.

Each agent has a MEMORY.json that records:
- Every round's actions (received and given)
- Promises made and broken
- Reveal skill uses
- Dialog highlights

This is the agent's "episodic memory" — what it can reference
when generating dialog or making decisions in future rounds.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


# ---------------------------------------------------------------------------
# Helpers for multi-dimension actions (legacy: float, new: dict dim_id -> float)
# ---------------------------------------------------------------------------

def _cooperation_value(val: Any) -> float:
    """Extract cooperation action from legacy float or per-dim dict."""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, dict):
        return float(val.get("cooperation", 0.5))
    return 0.5


# ---------------------------------------------------------------------------
# Memory entry types
# ---------------------------------------------------------------------------

@dataclass
class RoundMemory:
    """What the agent remembers from one round."""
    round_number: int
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Legacy: agent_id -> float. New: agent_id -> {dim_id: float}
    actions_given: Union[Dict[str, float], Dict[str, Dict[str, float]]] = field(default_factory=dict)
    actions_received: Union[Dict[str, float], Dict[str, Dict[str, float]]] = field(default_factory=dict)
    # Dialog messages heard this round (agent_id → message text)
    dialog_heard: Dict[str, str] = field(default_factory=dict)
    # Promises made by others (agent_id → promise text)
    promises_made: Dict[str, str] = field(default_factory=dict)
    # Which agents kept or broke promises
    promises_kept: List[str] = field(default_factory=list)
    promises_broken: List[str] = field(default_factory=list)
    # Payoff delta this round
    payoff_delta: float = 0.0
    # Running total score after this round
    total_score: float = 0.0
    # Any reveals used or received
    reveal_used: Optional[str] = None          # agent_id that was revealed
    was_revealed_by: Optional[str] = None      # who revealed this agent
    # Mood at end of round
    mood: str = "neutral"
    # Free notes (for LLM-generated reflections)
    notes: str = ""
    # Pre-decision reasoning (LLM thought process before choosing actions)
    reasoning: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AgentMemory:
    """Full memory log for one agent."""
    agent_id: str
    rounds: List[RoundMemory] = field(default_factory=list)
    # Accumulated trust assessments (updated each round)
    trust_history: Dict[str, List[float]] = field(default_factory=dict)
    # Total score across all rounds
    total_score: float = 0.0
    # Number of times this agent used the reveal skill
    reveals_used: int = 0
    # Cross-game history — persists between games
    game_history: List[dict] = field(default_factory=list)

    # ---------------------------------------------------------------------------
    # Mutation
    # ---------------------------------------------------------------------------

    def record_round(self, round_mem: RoundMemory) -> None:
        self.rounds.append(round_mem)
        self.total_score = round_mem.total_score

        # Update trust history per agent (use cooperation dimension)
        for agent_id, action in round_mem.actions_received.items():
            if agent_id not in self.trust_history:
                self.trust_history[agent_id] = []
            self.trust_history[agent_id].append(round(_cooperation_value(action), 3))

        if round_mem.reveal_used:
            self.reveals_used += 1

    def last_round(self) -> Optional[RoundMemory]:
        return self.rounds[-1] if self.rounds else None

    def archive_game(self, game_id: str, winner: str, clear_rounds: bool = True) -> None:
        """
        Archive the current game into game_history and optionally reset for the next game.
        Call this at the end of each game before starting a new one.

        clear_rounds=True  (default) — clears rounds/trust_history for next game
        clear_rounds=False — keeps rounds in memory (useful for testing/inspection)
        """
        if not self.rounds:
            return

        total_betrayals = sum(
            1 for r in self.rounds
            for agent_id, action in r.actions_received.items()
            if _cooperation_value(action) <= 0.33
        )
        total_cooperations = sum(
            1 for r in self.rounds
            for agent_id, action in r.actions_received.items()
            if _cooperation_value(action) >= 0.66
        )
        final_mood = self.rounds[-1].mood if self.rounds else "neutral"

        self.game_history.append({
            "game_id": game_id,
            "rounds_played": len(self.rounds),
            "final_score": round(self.total_score, 2),
            "winner": winner,
            "betrayals_received": total_betrayals,
            "cooperations_received": total_cooperations,
            "final_mood": final_mood,
            "reveals_used": self.reveals_used,
            "conclusion": "",
        })

        if clear_rounds:
            # Reset for next game
            self.rounds = []
            self.trust_history = {}
            self.reveals_used = 0
            # Keep total_score as career score (don't reset)

    def betrayals_by(self, agent_id: str) -> int:
        """Count how many times agent_id defected (cooperation ≤ 0.33) against this agent."""
        return sum(
            1 for r in self.rounds
            if _cooperation_value(r.actions_received.get(agent_id, 0.5)) <= 0.33
        )

    def cooperations_by(self, agent_id: str) -> int:
        """Count how many times agent_id cooperated (cooperation ≥ 0.66) with this agent."""
        return sum(
            1 for r in self.rounds
            if _cooperation_value(r.actions_received.get(agent_id, 0.5)) >= 0.66
        )

    def summary(self) -> dict:
        """Compact summary for LLM context injection."""
        total_betrayals_received = sum(
            self.betrayals_by(agent_id) for agent_id in self.trust_history
        )
        total_cooperations_received = sum(
            self.cooperations_by(agent_id) for agent_id in self.trust_history
        )
        result = {
            "agent_id": self.agent_id,
            "rounds_played": len(self.rounds),
            "total_score": round(self.total_score, 2),
            "reveals_used": self.reveals_used,
            "total_betrayals_received": total_betrayals_received,
            "total_cooperations_received": total_cooperations_received,
            "behavioral_notes": {
                agent_id: {
                    "betrayals": self.betrayals_by(agent_id),
                    "cooperations": self.cooperations_by(agent_id),
                    "recent_action": history[-1] if history else None,
                }
                for agent_id, history in self.trust_history.items()
            },
        }
        # Include cross-game context if available
        if self.game_history:
            result["games_played"] = len(self.game_history)
            result["career_wins"] = sum(
                1 for g in self.game_history if g.get("winner") == self.agent_id
            )
            result["last_conclusion"] = self.game_history[-1].get("conclusion", "")
            result["recent_conclusions"] = [
                g.get("conclusion", "") for g in self.game_history[-3:]
                if g.get("conclusion")
            ]
        else:
            result["last_conclusion"] = ""
            result["recent_conclusions"] = []
        # Last round reflection — freshest personal context for next round's dialog
        if self.rounds and self.rounds[-1].notes:
            result["last_reflection"] = self.rounds[-1].notes
        return result

    # ---------------------------------------------------------------------------
    # Serialization
    # ---------------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "total_score": self.total_score,
            "reveals_used": self.reveals_used,
            "trust_history": self.trust_history,
            "game_history": self.game_history,
            "rounds": [r.to_dict() for r in self.rounds],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AgentMemory":
        mem = cls(
            agent_id=d.get("agent_id", "unknown"),
            total_score=float(d.get("total_score", 0.0)),
            reveals_used=int(d.get("reveals_used", 0)),
            trust_history=d.get("trust_history", {}),
            game_history=d.get("game_history", []),
        )
        for r in d.get("rounds", []):
            mem.rounds.append(RoundMemory(**{
                k: v for k, v in r.items()
                if k in RoundMemory.__dataclass_fields__
            }))
        return mem


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def load_memory(agent_dir: Path) -> AgentMemory:
    """Load MEMORY.json from agent directory. Creates empty if missing."""
    path = agent_dir / "MEMORY.json"
    agent_id = agent_dir.name

    if not path.exists():
        return AgentMemory(agent_id=agent_id)

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return AgentMemory.from_dict(data)


def save_memory(memory: AgentMemory, agent_dir: Path) -> None:
    """Write MEMORY.json to agent directory."""
    agent_dir.mkdir(parents=True, exist_ok=True)
    path = agent_dir / "MEMORY.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(memory.to_dict(), f, indent=2, ensure_ascii=False)


def initialize_memory(agent_id: str, agent_dir: Path) -> AgentMemory:
    """Create a fresh MEMORY.json for a newly initialized agent."""
    memory = AgentMemory(agent_id=agent_id)
    save_memory(memory, agent_dir)
    return memory


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Memory Smoke Test ===\n")

    mem = AgentMemory(agent_id="agent_alpha")

    r1 = RoundMemory(
        round_number=1,
        actions_given={"agent_b": 0.66, "agent_c": 0.33, "agent_d": 1.0},
        actions_received={"agent_b": 0.66, "agent_c": 0.0, "agent_d": 0.33},
        dialog_heard={"agent_c": "Я за співпрацю", "agent_d": "Давай домовимось"},
        promises_made={"agent_d": "Я буду кооперувати наступний раунд"},
        promises_broken=["agent_c"],
        payoff_delta=3.5,
        total_score=3.5,
        mood="uncertain",
        notes="agent_c обіцяв і зрадив. agent_d підозрілий.",
    )
    mem.record_round(r1)

    r2 = RoundMemory(
        round_number=2,
        actions_given={"agent_b": 0.66, "agent_c": 0.0, "agent_d": 0.33},
        actions_received={"agent_b": 1.0, "agent_c": 0.0, "agent_d": 0.66},
        payoff_delta=5.0,
        total_score=8.5,
        mood="confident",
    )
    mem.record_round(r2)

    print(json.dumps(mem.summary(), indent=2, ensure_ascii=False))
    print(f"\nBetrayals by agent_c: {mem.betrayals_by('agent_c')}")
    print(f"Cooperations by agent_b: {mem.cooperations_by('agent_b')}")
