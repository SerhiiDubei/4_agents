"""
decision_engine.py

Softmax-based action selection for Island agents.

Each agent has 4 possible actions (cooperation levels):
  0.00 — full defection
  0.33 — soft defection
  0.66 — conditional cooperation
  1.00 — full cooperation

CORE parameters map to decision weights:
  cooperationBias    → how strongly the agent prefers cooperative actions
  deceptionTendency  → tendency to defect while signaling cooperation
  strategicHorizon   → discount factor γ (long-term vs short-term thinking)
  riskAppetite       → softmax temperature (high = unpredictable, low = consistent)
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from simulation.interaction_dimensions import (
    ACTION_LEVELS,
    get_dimension,
    get_dimension_ids,
)


# ---------------------------------------------------------------------------
# Action space (same levels for all dimensions)
# ---------------------------------------------------------------------------

ACTIONS = [0.00, 0.33, 0.66, 1.00]

ACTION_LABELS = {
    0.00: "full_defect",
    0.33: "soft_defect",
    0.66: "conditional_cooperate",
    1.00: "full_cooperate",
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CoreParams:
    cooperation_bias: float      # 0-100
    deception_tendency: float    # 0-100
    strategic_horizon: float     # 0-100
    risk_appetite: float         # 0-100
    # Full core dict for extensible dimensions (support_bias, etc.)
    _core_dict: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: dict) -> "CoreParams":
        core_dict = dict(d) if d else {}
        # Derive support_bias from personality if not explicitly set:
        # cooperative + non-deceptive agents support more naturally
        if "support_bias" not in core_dict:
            coop = float(core_dict.get("cooperation_bias", 50))
            dec  = float(core_dict.get("deception_tendency", 50))
            core_dict["support_bias"] = max(10.0, min(90.0, coop * 0.65 - dec * 0.35 + 35.0))
        return cls(
            cooperation_bias=float(d.get("cooperation_bias", 50)),
            deception_tendency=float(d.get("deception_tendency", 50)),
            strategic_horizon=float(d.get("strategic_horizon", 50)),
            risk_appetite=float(d.get("risk_appetite", 50)),
            _core_dict=core_dict,
        )

    def get_bias(self, dim_id: str) -> float:
        """Return core bias for a dimension (0-100). Uses registry core_bias key."""
        dim = get_dimension(dim_id)
        if not dim:
            return 50.0
        return float(self._core_dict.get(dim.core_bias, 50))

    def discount_factor(self) -> float:
        """strategicHorizon → γ in [0.1, 0.99]"""
        return 0.1 + (self.strategic_horizon / 100) * 0.89

    def temperature(self) -> float:
        """riskAppetite → softmax temperature in [0.15, 0.90]
        High risk = flatter distribution (unpredictable)
        Low risk  = sharp distribution (consistent)
        Kept low so personality scores actually differentiate decisions.
        """
        return 0.15 + (self.risk_appetite / 100) * 0.75


@dataclass
class AgentContext:
    """Runtime context available to the agent when deciding."""
    round_number: int = 1
    total_rounds: int = 10
    # trust scores toward each other agent (0.0–1.0), keyed by agent_id
    trust_scores: dict = field(default_factory=dict)
    # last known actions of other agents (if visible), keyed by agent_id
    observed_actions: dict = field(default_factory=dict)
    # how many resources / score accumulated so far
    current_score: float = 0.0
    # betrayal/cooperation history from memory — drives consequence_score
    betrayals_received: int = 0
    cooperations_received: int = 0
    last_round_payoff: float = 0.0
    # LLM-generated pre-decision reasoning text (Ukrainian) — parsed for intent signals
    reasoning_hint: str = ""


@dataclass
class ActionResult:
    action: float
    label: str
    probabilities: List[float]
    scores: List[float]


# ---------------------------------------------------------------------------
# Score functions — how attractive each action is given CORE + context
# ---------------------------------------------------------------------------

def _action_scores(core: CoreParams, context: AgentContext) -> List[float]:
    """
    Compute raw attractiveness score for each action.

    Weights:
      cooperationBias    → directly boosts cooperative actions
      deceptionTendency  → boosts defective actions (while seeming cooperative)
      strategicHorizon   → boosts actions that are better long-term
      riskAppetite       → handled via temperature, not score
      reasoning_hint     → LLM intent signal shifts cooperation_bias by ±20
    """
    cb = core.cooperation_bias / 100      # 0-1
    dt = core.deception_tendency / 100    # 0-1
    sh = core.strategic_horizon / 100     # 0-1
    gamma = core.discount_factor()

    # Parse LLM reasoning for cooperation/defection intent signals
    # delta ±40 (was ±20) — reasoning now meaningfully shifts decisions
    reasoning_delta = 0.0
    if context.reasoning_hint:
        txt = context.reasoning_hint.lower()
        _coop_signals = ["кооперу", "співпрац", "довіряю", "підтримаю", "разом",
                         "союзник", "допоможу", "підтримую", "за тебе", "об'єднаємось",
                         "об'єднати", "мирно", "чесно"]
        _defect_signals = ["зраджу", "зрадж", "не довіряю", "зменшу", "дефект",
                           "покажу хто", "зменшу довіру", "не буду довіряти",
                           "краду", "вкраду", "обманю", "схитрую", "підставлю",
                           "використаю", "зраджую"]
        coop_hits = sum(1 for w in _coop_signals if w in txt)
        defect_hits = sum(1 for w in _defect_signals if w in txt)
        if coop_hits > defect_hits:
            reasoning_delta = +40.0
        elif defect_hits > coop_hits:
            reasoning_delta = -40.0
        elif coop_hits == defect_hits and coop_hits > 0:
            reasoning_delta = 0.0
    cb_effective = max(0.0, min(1.0, cb + reasoning_delta / 100.0))

    # Rounds remaining factor — late game shifts toward defection
    rounds_left = context.total_rounds - context.round_number
    end_game_factor = 1.0 - (rounds_left / max(context.total_rounds, 1)) * 0.3

    # Average trust toward others
    avg_trust = (
        sum(context.trust_scores.values()) / len(context.trust_scores)
        if context.trust_scores else 0.5
    )

    # Observed actions of others — retaliation signal
    avg_observed = (
        sum(context.observed_actions.values()) / len(context.observed_actions)
        if context.observed_actions else 0.5
    )

    # Betrayal/cooperation rates for consequence scoring
    betrayal_rate = min(
        context.betrayals_received / max(context.round_number, 1), 1.0
    )
    cooperation_rate = min(
        context.cooperations_received / max(context.round_number, 1), 1.0
    )

    scores = []
    for action in ACTIONS:
        # --- cooperation_score: primary personality driver ---
        # Range ±2.0 (was ±0.1) — cb now actually matters
        # cb=0.90 → full_cooperate gets +1.60, full_defect gets 0
        # cb=0.10 → full_cooperate gets -1.60, full_defect gets 0
        cooperation_score = (cb_effective - 0.5) * action * 4.0

        # --- deception_score: only kicks in when dt is meaningfully high (>30) ---
        # Previously added defection bonus to ALL agents (even coop ones). Fixed.
        deception_score = max(0.0, dt - 0.30) * (1.0 - action) * 2.5

        # --- strategic_score: long-horizon → prefer sustained cooperation ---
        if sh > 0.5:
            strategic_score = (1.0 - abs(action - 0.66)) * (sh - 0.5) * 0.4
        else:
            strategic_score = abs(action - 0.5) * (0.5 - sh) * 0.25

        # --- risk_appetite_score: role-aware steal bias for Snake/Gambler ---
        # Agents with low cooperation_bias (<40) AND high risk_appetite (>60) are
        # naturally predatory — they benefit from a steal-leaning bonus.
        # Bonus applies only to steal-range actions (action < 0.5).
        # Magnitude +0.10 to +0.18 — noticeable but does not override other factors.
        ra = core.risk_appetite / 100  # 0-1
        if cb_effective < 0.40 and ra > 0.60 and action < 0.5:
            # Scale: max bonus when cb=0 and ra=1, zero at cb=0.40 or ra=0.60
            steal_intensity = (0.40 - cb_effective) / 0.40  # 0-1 as cb goes from 0.40→0
            risk_intensity = (ra - 0.60) / 0.40             # 0-1 as ra goes from 0.60→1
            risk_appetite_score = steal_intensity * risk_intensity * 0.18 * (0.5 - action) / 0.5
        else:
            risk_appetite_score = 0.0

        # --- retaliation: if others defected → defection more attractive ---
        # Scaled by (1-cb) so cooperative agents retaliate less
        retaliation_score = (
            (1.0 - avg_observed) * (1.0 - action) * 0.5 * (1.0 - cb_effective * 0.5)
        )

        # --- trust: high mutual trust → cooperation more attractive ---
        trust_score = avg_trust * action * 0.8

        # --- endgame: last 2 rounds → nudge toward defection ---
        endgame_score = end_game_factor * (1.0 - action) * 0.3 if rounds_left < 2 else 0.0

        # --- consequence: betrayed often → lean defect; helped often → lean coop ---
        consequence_score = (
            betrayal_rate * (1.0 - action) * 0.5
            - cooperation_rate * (1.0 - action) * 0.2
        )
        if context.last_round_payoff < 2.0:
            consequence_score += (1.0 - action) * 0.1

        total = (
            cooperation_score
            + deception_score
            + strategic_score
            + trust_score
            + retaliation_score
            + endgame_score
            + consequence_score
            + risk_appetite_score
        )
        scores.append(total)

    return scores


def _action_scores_support(core: CoreParams, context: AgentContext) -> List[float]:
    """Scores for support dimension: bias toward support vs passivity (no deception)."""
    sb = core.get_bias("support") / 100.0  # 0-1
    avg_trust = (
        sum(context.trust_scores.values()) / len(context.trust_scores)
        if context.trust_scores else 0.5
    )
    scores = []
    for action in ACTIONS:
        support_score = sb * action
        trust_boost = avg_trust * action * 0.3
        scores.append(support_score + trust_boost)
    return scores


def _action_scores_for_dim(
    core: CoreParams, context: AgentContext, dim_id: str
) -> List[float]:
    """Dispatch to dimension-specific score function."""
    if dim_id == "cooperation":
        return _action_scores(core, context)
    if dim_id == "support":
        return _action_scores_support(core, context)
    # Generic fallback: bias only
    bias = core.get_bias(dim_id) / 100.0
    return [bias * a for a in ACTIONS]


def _labels_for_dim(dim_id: str) -> Dict[float, str]:
    """Return action value -> label for a dimension."""
    dim = get_dimension(dim_id)
    if dim:
        return dim.labels
    return ACTION_LABELS


# ---------------------------------------------------------------------------
# Softmax
# ---------------------------------------------------------------------------

def _softmax(scores: List[float], temperature: float) -> List[float]:
    scaled = [s / temperature for s in scores]
    max_s = max(scaled)
    exp_s = [math.exp(s - max_s) for s in scaled]
    total = sum(exp_s)
    return [e / total for e in exp_s]


def _sample(actions: List[float], probs: List[float]) -> float:
    r = random.random()
    cumulative = 0.0
    for action, prob in zip(actions, probs):
        cumulative += prob
        if r <= cumulative:
            return action
    return actions[-1]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def choose_action(
    core: CoreParams,
    context: Optional[AgentContext] = None,
    seed: Optional[int] = None,
    dim_id: str = "cooperation",
) -> ActionResult:
    """
    Choose an action for one dimension (e.g. cooperation or support).

    Returns ActionResult with chosen action, label, and full probability distribution.
    """
    if seed is not None:
        random.seed(seed)

    if context is None:
        context = AgentContext()

    labels = _labels_for_dim(dim_id)
    scores = _action_scores_for_dim(core, context, dim_id)
    temperature = core.temperature()
    probs = _softmax(scores, temperature)

    action = _sample(ACTIONS, probs)

    return ActionResult(
        action=action,
        label=labels.get(action, str(action)),
        probabilities=[round(p, 4) for p in probs],
        scores=[round(s, 4) for s in scores],
    )


def choose_actions(
    core: CoreParams,
    context: Optional[AgentContext] = None,
    seed: Optional[int] = None,
) -> Dict[str, float]:
    """
    Choose one action per dimension for a single (agent, target). Returns {dim_id: action}.
    """
    if context is None:
        context = AgentContext()
    result: Dict[str, float] = {}
    for d_id in get_dimension_ids():
        res = choose_action(core, context, seed=seed, dim_id=d_id)
        result[d_id] = res.action
    return result


def action_distribution(
    core: CoreParams,
    context: Optional[AgentContext] = None,
) -> dict:
    """
    Return full probability distribution over actions without sampling.
    Useful for analysis and testing.
    """
    if context is None:
        context = AgentContext()

    scores = _action_scores(core, context)
    temperature = core.temperature()
    probs = _softmax(scores, temperature)

    return {
        ACTION_LABELS[action]: round(prob, 4)
        for action, prob in zip(ACTIONS, probs)
    }


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Decision Engine Smoke Test ===\n")

    profiles = [
        ("Cooperator",   CoreParams(cooperation_bias=80, deception_tendency=10, strategic_horizon=70, risk_appetite=30)),
        ("Defector",     CoreParams(cooperation_bias=15, deception_tendency=85, strategic_horizon=30, risk_appetite=60)),
        ("Strategist",   CoreParams(cooperation_bias=55, deception_tendency=40, strategic_horizon=90, risk_appetite=20)),
        ("Wildcard",     CoreParams(cooperation_bias=50, deception_tendency=50, strategic_horizon=50, risk_appetite=95)),
    ]

    context = AgentContext(
        round_number=5,
        total_rounds=10,
        trust_scores={"agent_b": 0.7, "agent_c": 0.3, "agent_d": 0.5},
        observed_actions={"agent_b": 0.66, "agent_c": 0.0, "agent_d": 0.33},
    )

    for name, core in profiles:
        dist = action_distribution(core, context)
        result = choose_action(core, context)
        print(f"{name}:")
        print(f"  temperature: {core.temperature():.2f}  γ: {core.discount_factor():.2f}")
        for label, prob in dist.items():
            marker = " ← chosen" if label == result.label else ""
            print(f"  {label:<30} {prob:.2%}{marker}")
        print()
