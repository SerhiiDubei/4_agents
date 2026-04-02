"""
TIME WARS constants — aligned with TIMER event model.
Event names use event_type for log/TIMER compatibility.
"""

# Time
DEFAULT_BASE_SECONDS_PER_PLAYER = 900   # 15 min
DEFAULT_GAME_DURATION_SEC = 900         # 15 min total game time
TICK_INTERVAL_SEC = 1                   # real-time tick

# Payoffs (seconds)
COOP_REWARD_EACH = 30                  # both get +30 on mutual cooperate
STEAL_SUCCESS_ACTOR_GAIN = 45
STEAL_SUCCESS_TARGET_LOSS = 30
STEAL_PARTIAL_ACTOR_GAIN = 20
STEAL_PARTIAL_TARGET_LOSS = 15
STEAL_FAIL_ACTOR_PENALTY = 15
BETRAYED_COOP_LOSS = 15
BETRAYER_COOP_GAIN = 60
MUTUAL_DEFECT_LOSS = 10

# Roll thresholds (d20)
STEAL_ROLL_SUCCESS_MIN = 15
STEAL_ROLL_PARTIAL_MIN = 8

# Mana (trust = mana; gain/loss per action)
COOP_MANA_EACH = 5           # both get +5 mana on cooperate
STEAL_MANA_SUCCESS_ACTOR = 8  # actor gains mana on successful steal
STEAL_MANA_FAIL_ACTOR = -3   # actor loses mana on failed steal
STARTING_MANA = 20
MANA_PER_ROUND = 1           # minimal passive fallback; primary mana from cooperate (+5 each)

# Event type names (TIMER-compatible)
EVENT_TYPE_COOPERATE = "cooperate"
EVENT_TYPE_STEAL = "steal"
EVENT_TYPE_SELF_ADD = "self_add"
EVENT_TYPE_CODE_USE = "code_use"
EVENT_TYPE_STORM = "storm"
EVENT_TYPE_CRISIS = "crisis"
EVENT_TYPE_SKILL_TRIGGER = "skill_trigger"
EVENT_TYPE_ELIMINATION = "elimination"
EVENT_TYPE_GAME_START = "game_start"
EVENT_TYPE_GAME_OVER = "game_over"
EVENT_TYPE_ROLE_ASSIGNMENT = "role_assignment"
EVENT_TYPE_CODE_BUY = "code_buy"
EVENT_TYPE_STATE_SNAPSHOT = "state_snapshot"
EVENT_TYPE_ROUND_START = "round_start"
EVENT_TYPE_PLAYER_INTENT = "player_intent"

# Action phase
ACTION_PHASE_INTERVAL_SEC = 30         # run action phase every N sec (or on event)

# Balance / simulation (1 tick = 1 "game minute" for pacing)
SECONDS_PER_GAME_MINUTE = 60           # 1 game minute = 60 sec (tick cost per player per tick)
DEFAULT_BALANCE_B_MINUTES = 20         # default start time per player (game minutes)
DEFAULT_BALANCE_T_TICKS = 20           # default game length (ticks = game minutes)

# ---------------------------------------------------------------------------
# Code manifest (CODE_MANIFEST.md) — classes and risk
# ---------------------------------------------------------------------------
from game_modes.time_wars.code_manifest import (
    X_MANA_PER_MINUTE,
    CODE_CLASS_C,
    CODE_CLASS_B,
    CODE_CLASS_A,
    CODE_CLASS_S,
    CODE_CLASS_COEFFICIENT,
    CODE_CLASS_PRICE_MIN,
    CODE_CLASS_PRICE_MAX,
    RISK_LEVEL_MULTIPLIER,
)
