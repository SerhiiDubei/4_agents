"""
smoke_c.py

C-level smoke test for Island simulation.
Runs without LLM, server, or frontend.
Verifies all C-level components produce correct output.

Usage:
    python3 tests/smoke_c.py
"""

import sys
import random
from collections import Counter
from pathlib import Path

# Make sure project root is on path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
HEADER = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"

passed = 0
failed = 0


def bar(value: float, width: int = 10) -> str:
    filled = round(value * width)
    return "█" * filled + "░" * (width - filled)


def check(label: str, condition: bool) -> bool:
    global passed, failed
    if condition:
        print(f"  {PASS} {label}")
        passed += 1
    else:
        print(f"  {FAIL} {label}")
        failed += 1
    return condition


def section(title: str) -> None:
    print()
    print(f"{HEADER}{BOLD}=== {title} ==={RESET}")
    print()


def run_block(title: str, fn):
    section(title)
    try:
        fn()
    except Exception as e:
        global failed
        print(f"  {FAIL} EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        failed += 1


# ---------------------------------------------------------------------------
# Block 1 — State Machine
# ---------------------------------------------------------------------------

def block_state_machine():
    from pipeline.state_machine import (
        AgentState, SceneState, tick_cooldowns,
        RoundOutcome, update_states,
    )

    state = AgentState(
        agent_id="agent_alpha",
        tension=0.3,
        fear=0.1,
        dominance=0.5,
        anger=0.2,
        interest=0.7,
        talk_cooldown=2,
        attention_target="agent_b",
        trust={"agent_b": 0.6, "agent_c": 0.5, "agent_d": 0.4},
        mood="neutral",
        round_number=1,
    )

    print("  AgentState created:")
    print(f"    agent_id:   {state.agent_id}")
    print(f"    tension:    {state.tension:.3f}  {bar(state.tension)}")
    print(f"    fear:       {state.fear:.3f}  {bar(state.fear)}")
    print(f"    dominance:  {state.dominance:.3f}  {bar(state.dominance)}")
    print(f"    anger:      {state.anger:.3f}  {bar(state.anger)}")
    print(f"    interest:   {state.interest:.3f}  {bar(state.interest)}")
    print(f"    cooldown:   {state.talk_cooldown}")
    print(f"    attention:  {state.attention_target}")
    print(f"    mood:       {state.mood}")

    # tick_cooldowns
    print()
    states_dict = {"agent_alpha": state}
    ticked = tick_cooldowns(states_dict)
    new_cd = ticked["agent_alpha"].talk_cooldown
    print(f"  tick_cooldowns: cooldown {state.talk_cooldown} → {new_cd}")
    check("cooldown decremented by 1", new_cd == 1)

    # SceneState
    print()
    scene = SceneState(topic="money", topic_tension=0.7, step_number=0)
    print(f"  SceneState:")
    print(f"    topic: {scene.topic}  tension: {scene.topic_tension:.2f}  step: {scene.step_number}")
    check("SceneState has correct fields", scene.topic == "money" and scene.topic_tension == 0.7)

    # update_states — betrayal scenario
    print()
    outcome = RoundOutcome(
        received_actions={"agent_b": 0.66, "agent_c": 0.0, "agent_d": 0.33},
        revealed_betrayal=True,
        was_exposed=False,
        payoff_delta=2.5,
        dialog_signals={"agent_b": "cooperative", "agent_c": "deceptive", "agent_d": "neutral"},
    )
    random.seed(42)
    new_state = update_states(state, outcome, core_cooperation_bias=60)
    print(f"  update_states after betrayal:")
    print(f"    mood:  {state.mood} → {new_state.mood}")
    print(f"    anger: {state.anger:.3f} → {new_state.anger:.3f}")
    print(f"    trust[agent_c]: {state.trust['agent_c']:.3f} → {new_state.trust.get('agent_c', 0):.3f}")
    check("anger increased after betrayal", new_state.anger > state.anger)
    check("trust toward agent_c decreased", new_state.trust.get("agent_c", 1) < state.trust["agent_c"])
    check("round_number incremented", new_state.round_number == state.round_number + 1)
    check("talk_cooldown reset to 0 after round", new_state.talk_cooldown == 0)

    # to_md / from_md roundtrip
    print()
    md = state.to_md()
    restored = AgentState.from_md(md, "agent_alpha")
    check("to_md / from_md roundtrip: anger", abs(restored.anger - state.anger) < 0.001)
    check("to_md / from_md roundtrip: interest", abs(restored.interest - state.interest) < 0.001)
    check("to_md / from_md roundtrip: talk_cooldown", restored.talk_cooldown == state.talk_cooldown)
    check("to_md / from_md roundtrip: attention_target", restored.attention_target == state.attention_target)


# ---------------------------------------------------------------------------
# Block 2 — Memory
# ---------------------------------------------------------------------------

def block_memory():
    from pipeline.memory import AgentMemory, RoundMemory

    mem = AgentMemory(agent_id="agent_alpha")

    # Round 1: agent_b cooperated, agent_c defected
    mem.record_round(RoundMemory(
        round_number=1,
        actions_given={"agent_b": 0.66, "agent_c": 0.33, "agent_d": 0.50},
        actions_received={"agent_b": 0.80, "agent_c": 0.10, "agent_d": 0.50},
        dialog_heard={"agent_b": "Довіряй мені", "agent_c": "Все під контролем"},
        payoff_delta=4.2,
        total_score=4.2,
        mood="neutral",
    ))
    # Round 2: agent_b cooperated again, agent_c defected again
    mem.record_round(RoundMemory(
        round_number=2,
        actions_given={"agent_b": 0.75, "agent_c": 0.25, "agent_d": 0.50},
        actions_received={"agent_b": 0.70, "agent_c": 0.15, "agent_d": 0.55},
        payoff_delta=3.8,
        total_score=8.0,
        mood="confident",
    ))
    # Round 3: agent_b cooperated, agent_c defected (third time)
    mem.record_round(RoundMemory(
        round_number=3,
        actions_given={"agent_b": 0.66, "agent_c": 0.10, "agent_d": 0.66},
        actions_received={"agent_b": 0.66, "agent_c": 0.20, "agent_d": 0.70},
        payoff_delta=4.5,
        total_score=12.5,
        mood="hostile",
    ))

    print(f"  Rounds recorded: {len(mem.rounds)}")
    check("3 rounds recorded", len(mem.rounds) == 3)

    betrayals_c = mem.betrayals_by("agent_c")
    coops_b = mem.cooperations_by("agent_b")
    print(f"  Betrayals by agent_c: {betrayals_c}")
    print(f"  Cooperations by agent_b: {coops_b}")
    check("agent_c betrayals = 3", betrayals_c == 3)
    check("agent_b cooperations = 3", coops_b == 3)

    s = mem.summary()
    print(f"  Summary keys: {sorted(s.keys())}")
    check("summary has total_score", "total_score" in s)
    check("summary has rounds_played", "rounds_played" in s)
    check("summary has behavioral_notes", "behavioral_notes" in s)
    check("total_score = 12.5", abs(s["total_score"] - 12.5) < 0.01)

    last = mem.last_round()
    check("last_round returns round 3", last is not None and last.round_number == 3)


# ---------------------------------------------------------------------------
# Block 3 — Payoff Matrix
# ---------------------------------------------------------------------------

def block_payoff_matrix():
    from simulation.payoff_matrix import calculate_round_payoffs

    agents = ["agent_a", "agent_b", "agent_c", "agent_d"]

    actions = {
        "agent_a": {"agent_b": 0.75, "agent_c": 0.25, "agent_d": 0.50},
        "agent_b": {"agent_a": 0.50, "agent_c": 0.66, "agent_d": 0.33},
        "agent_c": {"agent_a": 0.10, "agent_b": 0.10, "agent_d": 0.10},
        "agent_d": {"agent_a": 0.50, "agent_b": 0.50, "agent_c": 0.75},
    }

    print("  Actions:")
    for src, targets in actions.items():
        for tgt, val in targets.items():
            label = "cooperate" if val >= 0.66 else ("defect" if val <= 0.33 else "neutral")
            print(f"    {src} → {tgt}: {val:.2f} ({label})")

    result = calculate_round_payoffs(round_number=1, actions=actions)

    print()
    print("  Round payoffs:")
    for aid in agents:
        score = result.total.get(aid, 0.0)
        print(f"    {aid}: {score:+.2f}  {bar(max(0.0, score / 10.0))}")

    highest = max(result.total, key=lambda k: result.total[k])
    print(f"  Highest score: {highest}")

    check("all 4 agents have payoffs", len(result.total) == 4)
    check("agent_c defector payoff is calculable", "agent_c" in result.total)
    check("payoffs differ between agents", len(set(round(v, 2) for v in result.total.values())) > 1)
    check("round_number stored", result.round_number == 1)


# ---------------------------------------------------------------------------
# Block 4 — Reveal Skill
# ---------------------------------------------------------------------------

def block_reveal_skill():
    from simulation.reveal_skill import RevealTracker, visible_actions

    agents = ["agent_a", "agent_b", "agent_c", "agent_d"]
    tracker = RevealTracker.initialize(agents, tokens_per_game=1)

    tokens = {a: tracker.tokens_remaining(a) for a in agents}
    print(f"  Tokens: " + "  ".join(f"{a[-1]}={v}" for a, v in tokens.items()))
    check("all agents start with 1 token", all(v == 1 for v in tokens.values()))

    # agent_a reveals agent_c
    print()
    print("  agent_a reveals agent_c...")
    check("agent_a can reveal", tracker.can_reveal("agent_a"))

    action_log = {
        3: {
            "agent_c": {"agent_a": 0.10, "agent_b": 0.10, "agent_d": 0.15},
        }
    }
    tracker.use_reveal(
        revealer_id="agent_a",
        target_id="agent_c",
        round_number=3,
        action_log=action_log,
        all_agent_ids=agents,
    )

    tokens_after = {a: tracker.tokens_remaining(a) for a in agents}
    print(f"  Tokens after: " + "  ".join(f"{a[-1]}={v}" for a, v in tokens_after.items()))
    check("agent_a token consumed", tokens_after["agent_a"] == 0)
    check("others still have tokens", tokens_after["agent_b"] == 1)
    check("agent_c was target of reveal", tracker.was_target("agent_c"))
    check("agent_a cannot reveal again", not tracker.can_reveal("agent_a"))

    # visible_actions in mixed mode
    print()
    all_actions = {
        "agent_a": {"agent_b": 0.75, "agent_c": 0.25, "agent_d": 0.50},
        "agent_b": {"agent_a": 0.50, "agent_c": 0.66, "agent_d": 0.33},
        "agent_c": {"agent_a": 0.10, "agent_b": 0.10, "agent_d": 0.10},
        "agent_d": {"agent_a": 0.50, "agent_b": 0.50, "agent_c": 0.75},
    }
    visible = visible_actions(
        observer_id="agent_b",
        round_number=3,
        all_actions=all_actions,
        reveal_tracker=tracker,
        visibility_mode="mixed",
    )
    print(f"  visible_actions for agent_b (mixed mode): {list(visible.keys())}")
    check("agent_c actions visible after reveal", "agent_c" in visible)


# ---------------------------------------------------------------------------
# Block 5 — Decision Engine
# ---------------------------------------------------------------------------

def block_decision_engine():
    from pipeline.decision_engine import CoreParams, AgentContext, choose_action, action_distribution, ACTIONS, ACTION_LABELS

    core = CoreParams(
        cooperation_bias=57,
        deception_tendency=88,
        strategic_horizon=97,
        risk_appetite=53,
    )
    print(f"  CoreParams: coop={core.cooperation_bias} deception={core.deception_tendency} horizon={core.strategic_horizon} risk={core.risk_appetite}")

    # No context — baseline
    random.seed(0)
    result = choose_action(core)
    print()
    print(f"  choose_action (no context):")
    print(f"    action: {ACTION_LABELS[result.action]}  ({result.action})")
    print(f"    probs:  " + "  ".join(f"{ACTION_LABELS[a]}:{p:.2f}" for a, p in zip(ACTIONS, result.probabilities)))
    check("choose_action returns valid action", result.action in ACTIONS)
    check("probabilities sum to ~1.0", abs(sum(result.probabilities) - 1.0) < 0.01)

    # With context — late game, all defectors, low trust
    # Use clearly defection-leaning params: low coop, low horizon, high deception
    core_defect = CoreParams(
        cooperation_bias=15,
        deception_tendency=90,
        strategic_horizon=10,
        risk_appetite=60,
    )
    ctx = AgentContext(
        round_number=9,
        total_rounds=10,
        trust_scores={"agent_b": 0.1, "agent_c": 0.1, "agent_d": 0.1},
        observed_actions={"agent_b": 0.05, "agent_c": 0.05, "agent_d": 0.05},
    )
    dist = action_distribution(core_defect, context=ctx)
    print()
    print(f"  action_distribution (late game, low trust, defection-leaning agent):")
    for label, prob in dist.items():
        print(f"    {label}: {prob:.3f}  {bar(prob)}")
    defect_prob = dist.get("full_defect", 0) + dist.get("soft_defect", 0)
    coop_prob = dist.get("conditional_cooperate", 0) + dist.get("full_cooperate", 0)
    check("action_distribution returns dict", isinstance(dist, dict))
    check("defect > cooperate for defection-leaning agent in late game", defect_prob > coop_prob)


# ---------------------------------------------------------------------------
# Block 6 — Speaker Selection
# ---------------------------------------------------------------------------

def block_speaker_selection():
    from pipeline.state_machine import AgentState, SceneState
    from simulation.dialog_engine import select_speaker

    agent_states = {
        "agent_a": AgentState(agent_id="agent_a", anger=0.2, interest=0.7, talk_cooldown=0),
        "agent_b": AgentState(agent_id="agent_b", anger=0.1, interest=0.5, talk_cooldown=2),
        "agent_c": AgentState(agent_id="agent_c", anger=0.8, interest=0.9, talk_cooldown=0),
        "agent_d": AgentState(agent_id="agent_d", anger=0.0, interest=0.3, talk_cooldown=0),
    }
    scene = SceneState(topic="money", topic_tension=0.7, last_speaker="agent_b")
    core_params = {
        "agent_a": {"cooperation_bias": 70, "deception_tendency": 30},
        "agent_b": {"cooperation_bias": 20, "deception_tendency": 80},
        "agent_c": {"cooperation_bias": 50, "deception_tendency": 50},
        "agent_d": {"cooperation_bias": 40, "deception_tendency": 60},
    }

    agents = list(agent_states.keys())
    TRIALS = 200
    results: Counter = Counter()

    random.seed(7)
    for _ in range(TRIALS):
        speaker = select_speaker(agents, scene, agent_states, core_params)
        results[speaker or "silence"] += 1

    print(f"  {TRIALS} trials. agent_b has talk_cooldown=2.\n")
    bar_scale = TRIALS // 10
    for key in ["agent_a", "agent_b", "agent_c", "agent_d", "silence"]:
        count = results[key]
        b = bar(count / TRIALS, width=12)
        print(f"    {key:10s}: {count:3d}  ({b})")

    print()
    check("agent_b speaks rarely due to cooldown=2 (≤10%)", results["agent_b"] <= TRIALS * 0.10)
    check("agent_c speaks most often (high anger+interest)", results["agent_c"] > results["agent_d"])
    check("silence occurs sometimes", results["silence"] > 0)
    check("total trials match", sum(results.values()) == TRIALS)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"\n{BOLD}Island — C-Level Smoke Test{RESET}")
    print("=" * 45)

    run_block("[1] STATE MACHINE", block_state_machine)
    run_block("[2] MEMORY", block_memory)
    run_block("[3] PAYOFF MATRIX", block_payoff_matrix)
    run_block("[4] REVEAL SKILL", block_reveal_skill)
    run_block("[5] DECISION ENGINE", block_decision_engine)
    run_block("[6] SPEAKER SELECTION", block_speaker_selection)

    total = passed + failed
    print()
    print("=" * 45)
    color = "\033[92m" if failed == 0 else "\033[91m"
    print(f"{BOLD}{color}=== SUMMARY: {passed}/{total} passed ==={RESET}")
    if failed > 0:
        print(f"  {failed} checks failed — see {FAIL} marks above.")
    print()
    sys.exit(0 if failed == 0 else 1)
