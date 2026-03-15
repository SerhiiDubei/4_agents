"""
interaction_dimensions.py

Registry of interaction dimensions (axes) for the Island game.
Each dimension is one independent scale (e.g. cooperation, support) with its own
core params, payoff type, and labels. Adding a 3rd/4th dimension = add entry here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Default when no action is present (legacy or missing dim)
DEFAULT_ACTION_VALUE = 0.5

# Valid discrete action levels (used by decision_engine and reasoning snap)
ACTION_LEVELS = [0.0, 0.33, 0.66, 1.0]


@dataclass
class InteractionDimension:
    """One interaction axis (e.g. cooperation, support)."""
    id: str
    core_bias: str
    core_deception: Optional[str] = None
    payoff_type: str = "pd"
    weight: float = 1.0
    labels: Dict[float, str] = field(default_factory=dict)

    def label_for(self, value: float) -> str:
        """Return label for action value; snap to nearest level if needed."""
        if value in self.labels:
            return self.labels[value]
        nearest = min(ACTION_LEVELS, key=lambda a: abs(a - value))
        return self.labels.get(nearest, f"{value:.2f}")


# ---------------------------------------------------------------------------
# Registry: single source of truth for all dimensions
# ---------------------------------------------------------------------------

INTERACTION_DIMENSIONS: List[InteractionDimension] = [
    InteractionDimension(
        id="cooperation",
        core_bias="cooperation_bias",
        core_deception="deception_tendency",
        payoff_type="pd",
        weight=1.0,
        labels={
            0.0: "full_defect",
            0.33: "soft_defect",
            0.66: "conditional_cooperate",
            1.0: "full_cooperate",
        },
    ),
    InteractionDimension(
        id="support",
        core_bias="support_bias",
        core_deception=None,
        payoff_type="support",
        weight=0.5,
        labels={
            0.0: "passive",
            0.33: "low_support",
            0.66: "active_support",
            1.0: "full_support",
        },
    ),
]

_DIM_BY_ID: Dict[str, InteractionDimension] = {d.id: d for d in INTERACTION_DIMENSIONS}


def get_dimension_ids() -> List[str]:
    """Return ordered list of dimension ids (e.g. ['cooperation', 'support'])."""
    return [d.id for d in INTERACTION_DIMENSIONS]


def get_dimension(dim_id: str) -> Optional[InteractionDimension]:
    """Return dimension config by id, or None if unknown."""
    return _DIM_BY_ID.get(dim_id)


def get_default_action_value(dim_id: str) -> float:
    """Return default action value for a dimension (e.g. 0.5)."""
    return DEFAULT_ACTION_VALUE


def get_action_for_dim(
    actions: Dict,
    agent_id: str,
    target_id: str,
    dim_id: str,
) -> float:
    """
    Read action value for (agent, target, dim) with backward compatibility.

    actions can be:
      - Dict[agent_id, Dict[target_id, float]]  -> legacy: return only for dim_id == "cooperation"
      - Dict[agent_id, Dict[target_id, Dict[dim_id, float]]]  -> new format
    """
    agent_actions = actions.get(agent_id) or {}
    target_val = agent_actions.get(target_id)
    if target_val is None:
        return DEFAULT_ACTION_VALUE
    if isinstance(target_val, (int, float)):
        if dim_id == "cooperation":
            return float(target_val)
        return DEFAULT_ACTION_VALUE
    if isinstance(target_val, dict):
        return float(target_val.get(dim_id, DEFAULT_ACTION_VALUE))
    return DEFAULT_ACTION_VALUE


def normalize_actions_to_dimensions(
    actions_legacy: Dict[str, Dict[str, float]],
) -> Dict[str, Dict[str, Dict[str, float]]]:
    """
    Convert legacy {agent: {target: float}} to {agent: {target: {dim_id: float}}}.
    Puts the single float under "cooperation"; other dims get DEFAULT_ACTION_VALUE.
    """
    dim_ids = get_dimension_ids()
    out: Dict[str, Dict[str, Dict[str, float]]] = {}
    for agent_id, targets in actions_legacy.items():
        out[agent_id] = {}
        for target_id, val in targets.items():
            if isinstance(val, (int, float)):
                out[agent_id][target_id] = {
                    dim_id: float(val) if dim_id == "cooperation" else DEFAULT_ACTION_VALUE
                    for dim_id in dim_ids
                }
            else:
                out[agent_id][target_id] = {
                    dim_id: float(val.get(dim_id, DEFAULT_ACTION_VALUE))
                    for dim_id in dim_ids
                }
    return out
