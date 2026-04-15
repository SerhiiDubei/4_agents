"""
constants.py — єдине джерело правди для порогів та констант симуляції.

Раніше пороги були розкидані по 4 файлах:
  payoff_matrix.py   → 0.33 / 0.66
  dialog_engine.py   → 0.15 / 0.45 / 0.75
  reveal_skill.py    → 0.40 / 0.66
  reasoning.py       → 0.15 / 0.45 / 0.75

Тепер усі імпортують звідси.
"""

# ---------------------------------------------------------------------------
# Action levels — discrete cooperation values
# ---------------------------------------------------------------------------

ACTION_FULL_DEFECT = 0.00
ACTION_SOFT_DEFECT = 0.33
ACTION_CONDITIONAL_COOP = 0.66
ACTION_FULL_COOP = 1.00

ACTION_LEVELS = [ACTION_FULL_DEFECT, ACTION_SOFT_DEFECT, ACTION_CONDITIONAL_COOP, ACTION_FULL_COOP]

# ---------------------------------------------------------------------------
# Classification thresholds
# ---------------------------------------------------------------------------

# Used in payoff_matrix, reveal_skill for classifying outcomes
DEFECT_THRESHOLD = 0.33       # action <= this → defection / betrayal
COOPERATE_THRESHOLD = 0.66    # action >= this → cooperation

# Betrayal threshold for reveal trust delta calculation
REVEAL_BETRAYAL_THRESHOLD = 0.33   # aligned with DEFECT_THRESHOLD (was 0.40 — inconsistency fixed)

# Used in dialog/reasoning for narrative labels (more granular)
DIALOG_BETRAYAL_LABEL = 0.15       # <= this → "зрадив"
DIALOG_SOFT_DEFECT_LABEL = 0.45    # <= this → "м'яко зрадив"
DIALOG_SOFT_COOP_LABEL = 0.75      # <= this → "частково кооперував"
# > 0.75 → "повністю кооперував"

# Default action value when no info available
DEFAULT_ACTION_VALUE = 0.5

# ---------------------------------------------------------------------------
# Trust deltas (reveal skill)
# ---------------------------------------------------------------------------

REVEAL_TRUST_GAIN_PER_COOP = 0.08
REVEAL_TRUST_LOSS_PER_BETRAYAL = 0.15

# ---------------------------------------------------------------------------
# Role-based CORE parameter overlays (КРИТ-3)
# Застосовуються до базових CORE значень агента залежно від ролі.
# Це єдине джерело правди — використовується і в Island, і в Time Wars.
# ---------------------------------------------------------------------------

ROLE_CORE_OVERLAYS: dict[str, dict[str, float]] = {
    "role_snake":       {"cooperation_bias": -25, "deception_tendency": +30, "risk_appetite": +15},
    "role_gambler":     {"cooperation_bias": -30, "deception_tendency": +35, "risk_appetite": +30},
    "role_banker":      {"cooperation_bias": +20, "deception_tendency": -10},
    "role_peacekeeper": {"cooperation_bias": +25, "deception_tendency": -25, "risk_appetite": -10},
}
