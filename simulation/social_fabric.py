"""
social_fabric.py

Social action system for Island sim.

Two orthogonal concerns:
  - WHAT an agent does (quality: cooperate/betray) → decision_engine (unchanged)
  - WHO an agent acts toward + HOW MUCH    → SocialFabric (this module)

Key concepts:
  SocialAction   — one directed action: target + type + budget_value + visibility
  SocialState    — per-agent runtime state: budget pool + received history
  SocialFabric   — collection of all agents' social states

Budget formula:
  budget_total = budget_base + alpha * sum(received_last_round.values())
  capped at budget_base * CAP_MULTIPLIER

Trust auto-update (runs each round end):
  trust[sender] += TRUST_DELTA * action.value * vis_weight
  trust[others] → drift toward 0.5 at DRIFT_RATE
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Constants — tune these without changing logic
# ---------------------------------------------------------------------------

BUDGET_BASE: float = 1.0          # every agent starts with this per round
CAP_MULTIPLIER: float = 1.5       # budget can never exceed base * this
TRUST_DELTA_PER_VALUE: float = 0.12   # trust gained per 1.0 of action value
TRUST_DRIFT_RATE: float = 0.03    # passive drift toward 0.5 per round
DEFAULT_ALPHA: float = 0.5        # reciprocity sensitivity if not in CORE.json

VISIBILITY_WEIGHTS = {
    "public":  1.0,   # public actions affect trust fully
    "private": 0.7,   # private actions: target gets full, others can't see
}


# ---------------------------------------------------------------------------
# AgentTurnContext — what one agent knows when it MUST decide
# ---------------------------------------------------------------------------

@dataclass
class AgentTurnContext:
    """
    Regulated input for one agent's decision turn.

    Every round, each agent receives this context and MUST produce:
      - at least 1 SocialAction  (enforced by SocialFabric.enforce_minimum_action)
      - actions whose total value ≤ budget_pool  (enforced by normalize_actions)

    This structure is the single source of truth for what the agent
    is allowed to know when making social decisions.
    """
    agent_id: str
    round_number: int
    total_rounds: int
    peer_ids: List[str]                           # all other agents this round

    # Budget
    budget_pool: float                            # available to spend
    budget_carryover: float                       # how much was saved from last round

    # Social memory
    trust_scores: Dict[str, float]                # current trust toward each peer
    received_last_round: Dict[str, float]         # what positive actions came in last round
    actions_given_last: List[dict]                # what this agent declared last round

    # Dialog context (what the agent heard this round)
    public_messages: Dict[str, str]               # {sender_id: message_text}
    private_messages: Dict[str, str]              # {sender_id: dm_text} — only to this agent

    # Game context
    round_event: str = ""                         # shared event this round (situation)
    reasoning_hint: str = ""                      # LLM pre-decision thought (filled by reasoning.py)

    def must_act(self) -> bool:
        """Always True — agent is never allowed to skip their turn."""
        return True

    def budget_summary_str(self) -> str:
        leftover = round(self.budget_carryover, 3)
        return (
            f"budget={self.budget_pool} "
            f"(base=1.0 + carryover={leftover} + bonus from received)"
        )

    def to_llm_context(self) -> dict:
        """Serialize for injection into LLM prompt."""
        return {
            "round": self.round_number,
            "total_rounds": self.total_rounds,
            "budget_pool": self.budget_pool,
            "budget_carryover": self.budget_carryover,
            "trust": self.trust_scores,
            "received_last_round": self.received_last_round,
            "public_messages": self.public_messages,
            "private_messages": self.private_messages,
            "round_event": self.round_event,
            "must_declare": (
                f"You MUST declare at least 1 action toward one of: {self.peer_ids}. "
                f"Total value of all actions must not exceed {self.budget_pool}."
            ),
        }


ACTION_TYPES = {
    "share_food",
    "alliance",
    "warn",
    "ignore",
    "betray",
    "reciprocate",
    "deceive",
}


# ---------------------------------------------------------------------------
# SocialAction
# ---------------------------------------------------------------------------

@dataclass
class SocialAction:
    """One directed social action from an agent to a target."""
    target: str                     # agent_id of recipient
    type: str                       # one of ACTION_TYPES
    value: float                    # budget spent (0.0–budget_total)
    visibility: str = "public"      # "public" | "private"

    def __post_init__(self):
        if self.type not in ACTION_TYPES:
            raise ValueError(f"Unknown action type '{self.type}'. Valid: {ACTION_TYPES}")
        if not (0.0 <= self.value <= 10.0):  # loose upper bound, budget enforces real cap
            raise ValueError(f"Action value {self.value} out of range [0, 10]")
        if self.visibility not in VISIBILITY_WEIGHTS:
            raise ValueError(f"Visibility must be 'public' or 'private', got '{self.visibility}'")

    def vis_weight(self) -> float:
        return VISIBILITY_WEIGHTS[self.visibility]

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "type": self.type,
            "value": round(self.value, 3),
            "visibility": self.visibility,
        }


# ---------------------------------------------------------------------------
# SocialState  (per-agent, runtime)
# ---------------------------------------------------------------------------

@dataclass
class SocialState:
    """
    Runtime social state for one agent.

    Lives alongside AgentState (trust/betrayal counters).
    AgentState = what I think of others (trust scores)
    SocialState = how much I can invest + what I gave/received
    """
    agent_id: str
    budget_base: float = BUDGET_BASE
    alpha: float = DEFAULT_ALPHA          # reciprocity sensitivity from CORE.json
    budget_pool: float = BUDGET_BASE      # available this round
    budget_spent_last: float = 0.0        # how much was spent last round (for carryover)

    received_last_round: Dict[str, float] = field(default_factory=dict)
    actions_given_last: List[SocialAction] = field(default_factory=list)

    @classmethod
    def from_core(cls, agent_id: str, core: dict) -> "SocialState":
        """Create from CORE.json dict."""
        alpha = float(core.get("reciprocity_sensitivity", DEFAULT_ALPHA))
        return cls(agent_id=agent_id, alpha=alpha)

    def recalculate_budget(self) -> float:
        """
        Compute next round's budget with carryover.

        Formula:
          leftover  = max(0, pool_prev - spent_prev)
          bonus     = alpha * sum(received_last_round)   [positive actions only]
          new_pool  = min(leftover + base + bonus, cap)

        Carryover means: unspent budget accumulates — agent can save for a big move.
        Cap prevents unlimited hoarding.
        """
        received_sum = sum(self.received_last_round.values())
        leftover = max(0.0, self.budget_pool - self.budget_spent_last)
        bonus = self.alpha * received_sum
        raw = leftover + self.budget_base + bonus
        cap = self.budget_base * CAP_MULTIPLIER
        self.budget_pool = round(min(raw, cap), 4)
        return self.budget_pool

    def normalize_actions(self, actions: List[SocialAction]) -> List[SocialAction]:
        """
        If total budget spent > budget_pool, scale all values proportionally.
        Returns adjusted actions list (does NOT mutate input).
        """
        total = sum(a.value for a in actions)
        if total <= self.budget_pool or total == 0:
            return actions
        scale = self.budget_pool / total
        return [
            SocialAction(
                target=a.target,
                type=a.type,
                value=round(a.value * scale, 4),
                visibility=a.visibility,
            )
            for a in actions
        ]

    def budget_summary(self) -> dict:
        return {
            "agent": self.agent_id,
            "base": self.budget_base,
            "alpha": self.alpha,
            "received_last": dict(self.received_last_round),
            "bonus": round(self.alpha * sum(self.received_last_round.values()), 4),
            "pool": self.budget_pool,
            "cap": round(self.budget_base * CAP_MULTIPLIER, 4),
        }


# ---------------------------------------------------------------------------
# SocialFabric  (all agents together, one round)
# ---------------------------------------------------------------------------

@dataclass
class SocialFabric:
    """Collection of all agents' social states for one round."""
    states: Dict[str, SocialState] = field(default_factory=dict)

    def add(self, state: SocialState) -> None:
        self.states[state.agent_id] = state

    def get(self, agent_id: str) -> Optional[SocialState]:
        return self.states.get(agent_id)

    def enforce_minimum_action(
        self,
        agent_id: str,
        actions: List[SocialAction],
        peer_ids: List[str],
    ) -> List[SocialAction]:
        """
        Ensures agent always declares at least one action.

        If actions is empty → inject a minimal 'ignore' toward
        the peer with the lowest trust (or random if no trust data).
        This keeps the social graph active — passive silence is not allowed.

        Why mandatory: without enforcement, LLM may produce empty lists
        when uncertain, causing trust to stagnate and budget to silently accumulate.
        Every agent MUST make a social choice each round.
        """
        if actions:
            return actions
        if not peer_ids:
            return actions
        # Default: ignore the first peer (cheapest — spends 0 budget but logs the intent)
        default_target = peer_ids[0]
        return [SocialAction(target=default_target, type="ignore", value=0.0, visibility="public")]

    def apply_round(
        self,
        round_actions: Dict[str, List[SocialAction]],
        trust_map: Dict[str, Dict[str, float]],
    ) -> Dict[str, Dict[str, float]]:
        """
        Process one round of social actions:
          1. Record what each agent received
          2. Auto-update trust scores
          3. Recalculate budgets for next round

        Args:
            round_actions: {agent_id: [SocialAction, ...]} — declared this round
            trust_map: {agent_id: {peer_id: trust_float}} — mutable, updated in place

        Returns:
            Updated trust_map
        """
        # Positive actions: contribute to receiver's budget bonus + increase trust
        POSITIVE_TYPES = {"share_food", "alliance", "reciprocate"}
        # Negative actions: actively reduce trust (regardless of value)
        NEGATIVE_TYPES = {"betray", "warn", "deceive"}
        TRUST_PENALTY = -0.08   # fixed trust hit per negative action

        # Step 1 — collect received values per agent (positives only for budget)
        received: Dict[str, Dict[str, float]] = {aid: {} for aid in self.states}

        for sender_id, actions in round_actions.items():
            state = self.states.get(sender_id)
            if state:
                state.actions_given_last = actions

            for action in actions:
                target = action.target
                if target in received and action.type in POSITIVE_TYPES:
                    received[target][sender_id] = received[target].get(sender_id, 0.0) + action.value

        # Step 2 — update trust
        all_agents = set(self.states.keys())
        for agent_id, senders in received.items():
            if agent_id not in trust_map:
                trust_map[agent_id] = {}

            agent_trust = trust_map[agent_id]

            # Active update: agents who gave this agent something (positive)
            for sender_id, value in senders.items():
                vis_w = 1.0
                for action in round_actions.get(sender_id, []):
                    if action.target == agent_id:
                        vis_w = action.vis_weight()
                        break
                delta = TRUST_DELTA_PER_VALUE * value * vis_w
                current = agent_trust.get(sender_id, 0.5)
                agent_trust[sender_id] = round(min(1.0, current + delta), 4)

            # Negative actions: reduce trust directly
            for sender_id, actions in round_actions.items():
                if sender_id == agent_id:
                    continue
                for action in actions:
                    if action.target == agent_id and action.type in NEGATIVE_TYPES:
                        current = agent_trust.get(sender_id, 0.5)
                        agent_trust[sender_id] = round(max(0.0, current + TRUST_PENALTY), 4)

            # Passive drift: agents NOT in senders drift toward 0.5
            for peer_id in all_agents:
                if peer_id == agent_id or peer_id in senders:
                    continue
                current = agent_trust.get(peer_id, 0.5)
                if current != 0.5:
                    drift = TRUST_DRIFT_RATE * (0.5 - current)
                    agent_trust[peer_id] = round(current + drift, 4)

        # Step 3 — record spent, store received, recalculate budgets
        for agent_id, state in self.states.items():
            spent = sum(a.value for a in round_actions.get(agent_id, []))
            state.budget_spent_last = round(spent, 4)
            state.received_last_round = received.get(agent_id, {})
            state.recalculate_budget()

        return trust_map
