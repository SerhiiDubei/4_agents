"""
reveal_skill.py

The Reveal Skill — each agent can use it once per game.

Effect: the revealer privately learns the actual action history of one target agent.
No one else knows. The information is only used to update the revealer's own trust.

Mechanics:
  - Each agent gets 1 reveal token per game
  - Using reveal: revealer privately sees target's full action history
  - Only the revealer's trust toward target is updated — no public exposure
  - No "witnesses" — this is an intelligence-gathering action, not an accusation

Strategic use cases:
  - Verify if someone who seems cooperative is actually defecting
  - Decide whether to retaliate or continue trusting
  - Gain private information advantage before the final rounds
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RevealRecord:
    """One private use of the reveal skill."""
    round_number: int
    revealer_id: str        # who used the skill
    target_id: str          # who was investigated
    # The privately seen action history: {round: {toward_agent: action}}
    exposed_history: Dict[int, Dict[str, float]] = field(default_factory=dict)
    # trust_delta applied to revealer's trust toward target after seeing history
    trust_delta_applied: float = 0.0

    def summary(self) -> str:
        if not self.exposed_history:
            return f"{self.revealer_id} investigated {self.target_id} — no data"
        lines = [f"{self.revealer_id} privately investigated {self.target_id} (round {self.round_number}):"]
        for rnd, actions in sorted(self.exposed_history.items()):
            for target, val in actions.items():
                lines.append(f"  Round {rnd} → {target}: {val:.2f}")
        if self.trust_delta_applied != 0.0:
            lines.append(f"  Trust delta applied: {self.trust_delta_applied:+.2f}")
        return "\n".join(lines)


@dataclass
class RevealTracker:
    """Tracks reveal skill usage across all agents in a game."""
    # {agent_id: reveals_remaining}
    tokens: Dict[str, int] = field(default_factory=dict)
    # All reveals that happened this game (private log, not broadcast)
    history: List[RevealRecord] = field(default_factory=list)

    @classmethod
    def initialize(cls, agent_ids: List[str], tokens_per_game: int = 1) -> "RevealTracker":
        return cls(tokens={agent_id: tokens_per_game for agent_id in agent_ids})

    def can_reveal(self, agent_id: str) -> bool:
        return self.tokens.get(agent_id, 0) > 0

    def tokens_remaining(self, agent_id: str) -> int:
        return self.tokens.get(agent_id, 0)

    def use_reveal(
        self,
        revealer_id: str,
        target_id: str,
        round_number: int,
        action_log: Dict[int, Dict[str, Dict[str, float]]],
        all_agent_ids: List[str],
    ) -> Optional[RevealRecord]:
        """
        Execute the reveal skill — private intelligence gathering.

        action_log: {round_number: {agent_id: {other_agent_id: action}}}
        Returns RevealRecord with the private information if successful, None if no tokens.

        The record is stored in history but NOT broadcast to other agents.
        The caller (game_engine) is responsible for updating only the revealer's trust.
        """
        if not self.can_reveal(revealer_id):
            return None

        # Extract target's full action history
        exposed: Dict[int, Dict[str, float]] = {}
        for rnd, round_actions in action_log.items():
            if target_id in round_actions:
                exposed[rnd] = dict(round_actions[target_id])

        # Calculate trust delta based on observed betrayals toward revealer
        betrayals_toward_revealer = sum(
            1 for rnd_actions in exposed.values()
            if rnd_actions.get(revealer_id, 0.5) < 0.4
        )
        cooperations_toward_revealer = sum(
            1 for rnd_actions in exposed.values()
            if rnd_actions.get(revealer_id, 0.5) >= 0.66
        )
        rounds_observed = len(exposed)

        if rounds_observed > 0:
            trust_delta = (
                cooperations_toward_revealer * 0.08
                - betrayals_toward_revealer * 0.15
            )
        else:
            trust_delta = 0.0

        record = RevealRecord(
            round_number=round_number,
            revealer_id=revealer_id,
            target_id=target_id,
            exposed_history=exposed,
            trust_delta_applied=round(trust_delta, 3),
        )

        self.history.append(record)
        self.tokens[revealer_id] -= 1

        return record

    def was_investigated_by(self, revealer_id: str, target_id: str) -> bool:
        """Check if revealer has already investigated target."""
        return any(
            r.revealer_id == revealer_id and r.target_id == target_id
            for r in self.history
        )

    def was_target(self, agent_id: str) -> bool:
        """Check if agent was ever the target of a reveal (private — revealer knows, not target)."""
        return any(r.target_id == agent_id for r in self.history)

    def get_reveals_for_round(self, round_number: int) -> List[RevealRecord]:
        return [r for r in self.history if r.round_number == round_number]

    def to_dict(self) -> dict:
        return {
            "tokens": self.tokens,
            "history": [
                {
                    "round": r.round_number,
                    "revealer": r.revealer_id,
                    "target": r.target_id,
                    "trust_delta": r.trust_delta_applied,
                    "exposed_rounds": list(r.exposed_history.keys()),
                }
                for r in self.history
            ],
        }


# ---------------------------------------------------------------------------
# Visibility rules
# ---------------------------------------------------------------------------

def visible_actions(
    observer_id: str,
    round_number: int,
    all_actions: Dict[str, Dict[str, float]],
    reveal_tracker: RevealTracker,
    visibility_mode: str = "mixed",
) -> Dict[str, Dict[str, float]]:
    """
    Determine what actions are visible to a specific observer.

    visibility_mode:
      "full"   — everyone sees everything (testing only)
      "none"   — no one sees anything
      "mixed"  — default: you see only actions directed toward you
                  (reveal is now private, does NOT add public visibility)

    Returns: {agent_id: {toward_agent_id: action}} for visible actions only.
    """
    if visibility_mode == "full":
        return all_actions

    visible: Dict[str, Dict[str, float]] = {}

    for agent_id, agent_actions in all_actions.items():
        if agent_id == observer_id:
            continue

        visible_agent: Dict[str, float] = {}

        if visibility_mode == "mixed":
            # Can only see actions directed toward you
            for target_id, action_val in agent_actions.items():
                if target_id == observer_id:
                    visible_agent[target_id] = action_val

        if visible_agent:
            visible[agent_id] = visible_agent

    return visible


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    agents = ["agent_a", "agent_b", "agent_c", "agent_d"]
    tracker = RevealTracker.initialize(agents, tokens_per_game=1)

    # Simulate action log
    action_log = {
        1: {
            "agent_a": {"agent_b": 1.0, "agent_c": 0.66, "agent_d": 0.33},
            "agent_b": {"agent_a": 0.0, "agent_c": 0.66, "agent_d": 0.66},
            "agent_c": {"agent_a": 0.66, "agent_b": 0.33, "agent_d": 1.0},
            "agent_d": {"agent_a": 0.33, "agent_b": 0.66, "agent_c": 0.66},
        }
    }

    print("Tokens before:", tracker.tokens)
    print()

    record = tracker.use_reveal(
        revealer_id="agent_c",
        target_id="agent_b",
        round_number=1,
        action_log=action_log,
        all_agent_ids=agents,
    )

    if record:
        print(record.summary())

    print("\nTokens after:", tracker.tokens)
    print("agent_b was exposed:", tracker.was_exposed("agent_b"))
    print("agent_c was exposed:", tracker.was_exposed("agent_c"))

    print("\nVisible actions for agent_a (mixed mode):")
    visible = visible_actions(
        observer_id="agent_a",
        round_number=1,
        all_actions=action_log[1],
        reveal_tracker=tracker,
        visibility_mode="mixed",
    )
    import json
    print(json.dumps(visible, indent=2))
