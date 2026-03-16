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

# Action phase
ACTION_PHASE_INTERVAL_SEC = 30         # run action phase every N sec (or on event)
