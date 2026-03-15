"""
payoff_matrix.py

Payoff calculation for Island's 4-agent Stochastic Game.

Supports multiple interaction dimensions (see simulation/interaction_dimensions.py).
Each dimension has its own payoff type (pd, support, ...). Total payoff per pair
is the weighted sum over dimensions.

Legacy: actions can be {agent: {target: float}} — treated as cooperation only.
New:    actions are {agent: {target: {dim_id: float}}}.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from simulation.interaction_dimensions import (
    get_action_for_dim,
    get_dimension,
    get_dimension_ids,
    normalize_actions_to_dimensions,
)


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


def _pair_payoff_pd(action_i: float, action_j: float) -> Tuple[float, float]:
    """
    PD payoffs for one pair (bilinear interpolation). Returns (payoff_i, payoff_j).
    """
    payoff_i = (
        action_j * (action_i * R + (1 - action_i) * T)
        + (1 - action_j) * (action_i * S + (1 - action_i) * P)
    )
    payoff_j = (
        action_i * (action_j * R + (1 - action_j) * T)
        + (1 - action_i) * (action_j * S + (1 - action_j) * P)
    )
    return (round(payoff_i, 4), round(payoff_j, 4))


# Support dimension: mutual support = high, one supports = medium, both passive = low
# (1,1)->4 each, (1,0)/(0,1)->2 each, (0,0)->0.5 each (bilinear)
_SUP_R = 4.0   # both support
_SUP_T = 2.5   # you support, other passive (you get medium)
_SUP_S = 2.0   # you passive, other supports
_SUP_P = 0.5   # both passive


def _pair_payoff_support(action_i: float, action_j: float) -> Tuple[float, float]:
    """Support/passivity payoffs: rewards mutual support, bilinear interpolation."""
    payoff_i = (
        action_j * (action_i * _SUP_R + (1 - action_i) * _SUP_T)
        + (1 - action_j) * (action_i * _SUP_S + (1 - action_i) * _SUP_P)
    )
    payoff_j = (
        action_i * (action_j * _SUP_R + (1 - action_j) * _SUP_T)
        + (1 - action_i) * (action_j * _SUP_S + (1 - action_j) * _SUP_P)
    )
    return (round(payoff_i, 4), round(payoff_j, 4))


def _pair_payoff_for_dim(
    dim_id: str, action_i: float, action_j: float
) -> Tuple[float, float]:
    """Dispatch to the right payoff function by dimension payoff_type."""
    dim = get_dimension(dim_id)
    if not dim:
        return (0.0, 0.0)
    if dim.payoff_type == "pd":
        return _pair_payoff_pd(action_i, action_j)
    if dim.payoff_type == "support":
        return _pair_payoff_support(action_i, action_j)
    return (0.0, 0.0)


def _pair_payoff(
    agent_i: str,
    agent_j: str,
    action_i: float,
    action_j: float,
) -> PairPayoff:
    """
    Calculate payoffs for one pair (cooperation dimension only).
    Used for backward-compat summary and single-dim callers.
    """
    outcome = _classify_outcome(action_i, action_j)
    payoff_i, payoff_j = _pair_payoff_pd(action_i, action_j)
    return PairPayoff(
        agent_i=agent_i,
        agent_j=agent_j,
        action_i=action_i,
        action_j=action_j,
        payoff_i=payoff_i,
        payoff_j=payoff_j,
        outcome=outcome,
    )


def _is_legacy_actions(actions: Any) -> bool:
    """True if actions are legacy {agent: {target: float}}."""
    if not actions:
        return True
    for agent, targets in actions.items():
        if not targets:
            continue
        first_val = next(iter(targets.values()))
        return isinstance(first_val, (int, float))
    return True


def calculate_round_payoffs(
    round_number: int,
    actions: Any,
) -> RoundPayoffs:
    """
    Calculate payoffs for all agents in a round (all dimensions).

    actions: either
      {agent_id: {other_agent_id: float}}  (legacy: cooperation only)
      {agent_id: {other_agent_id: {dim_id: float}}}  (new: all dimensions)
    """
    if _is_legacy_actions(actions):
        actions = normalize_actions_to_dimensions(actions)

    agent_ids = list(actions.keys())
    total: Dict[str, float] = {a: 0.0 for a in agent_ids}
    pairs: List[PairPayoff] = []
    dim_ids = get_dimension_ids()

    processed = set()
    for i in agent_ids:
        for j in agent_ids:
            if i == j:
                continue
            pair_key = tuple(sorted([i, j]))
            if pair_key in processed:
                continue
            processed.add(pair_key)

            pair_payoff_i = 0.0
            pair_payoff_j = 0.0
            coop_i, coop_j = 0.5, 0.5

            for dim_id in dim_ids:
                dim = get_dimension(dim_id)
                if not dim:
                    continue
                action_i = get_action_for_dim(actions, i, j, dim_id)
                action_j = get_action_for_dim(actions, j, i, dim_id)
                if dim_id == "cooperation":
                    coop_i, coop_j = action_i, action_j
                pi, pj = _pair_payoff_for_dim(dim_id, action_i, action_j)
                pair_payoff_i += dim.weight * pi
                pair_payoff_j += dim.weight * pj

            outcome = _classify_outcome(coop_i, coop_j)
            pairs.append(
                PairPayoff(
                    agent_i=i,
                    agent_j=j,
                    action_i=coop_i,
                    action_j=coop_j,
                    payoff_i=round(pair_payoff_i, 4),
                    payoff_j=round(pair_payoff_j, 4),
                    outcome=outcome,
                )
            )
            total[i] += pair_payoff_i
            total[j] += pair_payoff_j

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
