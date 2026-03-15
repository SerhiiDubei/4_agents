"""
payoff_matrix.py

Payoff calculation for Island's 4-agent Stochastic Game.

Each agent makes one action toward each other agent simultaneously.
Actions are continuous values: 0.0 (full defect) → 1.0 (full cooperate).

Payoff follows the classic Prisoner's Dilemma structure:
  T > R > P > S  and  2R > T + S

  T = 7.0  Temptation  — you defect, other cooperates  (best for defector)
  R = 5.0  Reward      — both cooperate                (mutually good)
  P = 2.0  Punishment  — both defect                   (mutually bad)
  S = 0.5  Sucker      — you cooperate, other defects  (worst for cooperator)

For continuous actions (0.0–1.0) payoffs are bilinearly interpolated
between the four corner values, preserving the T>R>P>S ordering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


# ---------------------------------------------------------------------------
# Classic PD payoff values
# ---------------------------------------------------------------------------

T = 7.0   # Temptation  (defect vs cooperate)
R = 5.0   # Reward      (cooperate vs cooperate)
P = 2.0   # Punishment  (defect vs defect)
S = 0.5   # Sucker      (cooperate vs defect)

# Sanity check at import time
assert T > R > P > S, "PD ordering violated: need T > R > P > S"
assert 2 * R > T + S, "PD cooperation condition violated: need 2R > T + S"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PairPayoff:
    agent_i: str
    agent_j: str
    action_i: float   # action of i toward j
    action_j: float   # action of j toward i
    payoff_i: float
    payoff_j: float
    outcome: str      # "mutual_coop" | "mutual_defect" | "exploit_i" | "exploit_j" | "mixed"


@dataclass
class RoundPayoffs:
    round_number: int
    # {agent_id: total payoff this round}
    total: Dict[str, float] = field(default_factory=dict)
    # All pair-level breakdowns
    pairs: List[PairPayoff] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "round": self.round_number,
            "payoffs": {k: round(v, 3) for k, v in self.total.items()},
            "pair_outcomes": [
                {
                    "pair": f"{p.agent_i}→{p.agent_j}",
                    "actions": f"{p.action_i:.2f}/{p.action_j:.2f}",
                    "payoffs": f"{p.payoff_i:.2f}/{p.payoff_j:.2f}",
                    "outcome": p.outcome,
                }
                for p in self.pairs
            ],
        }


# ---------------------------------------------------------------------------
# Core calculation
# ---------------------------------------------------------------------------

def _classify_outcome(action_i: float, action_j: float) -> str:
    if action_i >= 0.66 and action_j >= 0.66:
        return "mutual_coop"
    if action_i <= 0.33 and action_j <= 0.33:
        return "mutual_defect"
    if action_i >= 0.66 and action_j <= 0.33:
        return "exploit_j"   # j exploits cooperating i
    if action_j >= 0.66 and action_i <= 0.33:
        return "exploit_i"   # i exploits cooperating j
    return "mixed"


def _pair_payoff(
    agent_i: str,
    agent_j: str,
    action_i: float,
    action_j: float,
) -> PairPayoff:
    """
    Calculate payoffs for one pair using bilinear interpolation over T/R/P/S.

    The four corners of the (action_i, action_j) unit square map to:
      (0,0) → both defect   → (P, P)
      (1,1) → both coop     → (R, R)
      (0,1) → i defects     → (T, S)  i gets Temptation, j gets Sucker
      (1,0) → j defects     → (S, T)  i gets Sucker, j gets Temptation

    Bilinear interpolation preserves T>R>P>S for all intermediate values.
    """
    outcome = _classify_outcome(action_i, action_j)

    # Bilinear interpolation
    # payoff_i: when action_j=0 (defects) i can get T(defect) or S(coop)
    #           when action_j=1 (coops)   i can get P(defect) or R(coop)
    payoff_i = (
        action_j * (action_i * R + (1 - action_i) * T)
        + (1 - action_j) * (action_i * S + (1 - action_i) * P)
    )
    payoff_j = (
        action_i * (action_j * R + (1 - action_j) * T)
        + (1 - action_i) * (action_j * S + (1 - action_j) * P)
    )

    return PairPayoff(
        agent_i=agent_i,
        agent_j=agent_j,
        action_i=action_i,
        action_j=action_j,
        payoff_i=round(payoff_i, 4),
        payoff_j=round(payoff_j, 4),
        outcome=outcome,
    )


def calculate_round_payoffs(
    round_number: int,
    actions: Dict[str, Dict[str, float]],
) -> RoundPayoffs:
    """
    Calculate payoffs for all agents in a round.

    actions: {agent_id: {other_agent_id: action_value}}
    Example:
      {
        "agent_a": {"agent_b": 0.66, "agent_c": 0.33, "agent_d": 1.0},
        "agent_b": {"agent_a": 0.33, "agent_c": 0.66, "agent_d": 0.66},
        ...
      }
    """
    agent_ids = list(actions.keys())
    total: Dict[str, float] = {a: 0.0 for a in agent_ids}
    pairs: List[PairPayoff] = []

    # Iterate over unique pairs
    processed = set()
    for i in agent_ids:
        for j in agent_ids:
            if i == j:
                continue
            pair_key = tuple(sorted([i, j]))
            if pair_key in processed:
                continue
            processed.add(pair_key)

            action_i = actions.get(i, {}).get(j, 0.5)
            action_j = actions.get(j, {}).get(i, 0.5)

            pair = _pair_payoff(i, j, action_i, action_j)
            pairs.append(pair)

            total[i] += pair.payoff_i
            total[j] += pair.payoff_j

    # Round totals
    for agent_id in total:
        total[agent_id] = round(total[agent_id], 4)

    return RoundPayoffs(round_number=round_number, total=total, pairs=pairs)


def payoff_table() -> str:
    """
    Print a human-readable payoff table for all action combinations.
    Useful for calibration and documentation.
    """
    labels = {0.00: "defect", 0.33: "soft_D", 0.66: "soft_C", 1.00: "coop"}
    actions = [0.00, 0.33, 0.66, 1.00]

    lines = [
        f"Payoff table — PD values: T={T} R={R} P={P} S={S}",
        f"Condition check: T>R>P>S = {T}>{R}>{P}>{S} ✓   2R>T+S = {2*R}>{T+S} ✓",
        "(i action / payoff_i / payoff_j):",
        "",
    ]
    header = "i\\j       " + "".join(f"{labels[a]:<14}" for a in actions)
    lines.append(header)

    for ai in actions:
        row = f"{labels[ai]:<10}"
        for aj in actions:
            pair = _pair_payoff("i", "j", ai, aj)
            row += f"{pair.payoff_i:+.1f}/{pair.payoff_j:+.1f}  "
        lines.append(row)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(payoff_table())
    print()

    actions = {
        "agent_a": {"agent_b": 1.00, "agent_c": 0.66, "agent_d": 0.33},
        "agent_b": {"agent_a": 0.00, "agent_c": 0.66, "agent_d": 0.66},
        "agent_c": {"agent_a": 0.66, "agent_b": 0.66, "agent_d": 1.00},
        "agent_d": {"agent_a": 0.33, "agent_b": 0.66, "agent_c": 0.66},
    }

    result = calculate_round_payoffs(round_number=1, actions=actions)

    import json
    print("Round 1 payoffs:")
    print(json.dumps(result.summary(), indent=2))
