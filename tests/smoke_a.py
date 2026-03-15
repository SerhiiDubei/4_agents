"""
smoke_a.py

A-level smoke test for Island simulation.
Verifies talk_transition matrix and its integration into the dialog engine.

No LLM calls. No disk I/O.

Usage:
    python3 tests/smoke_a.py
"""

import sys
import random
from collections import Counter
from pathlib import Path
from unittest.mock import patch

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
    filled = round(max(0.0, min(1.0, value)) * width)
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
# Block 1 — Tone Classification
# ---------------------------------------------------------------------------

def block_tone_classification():
    from pipeline.talk_transition import classify_tone, Tone

    cases = [
        ("довіряю тобі повністю",   False, Tone.FRIENDLY,   "friendly keywords"),
        ("разом ми впораємось",     False, Tone.FRIENDLY,   "friendly: разом"),
        ("обережно, я попереджаю",  False, Tone.AGGRESSIVE, "aggressive keywords"),
        ("зрадник, заплатиш",       False, Tone.AGGRESSIVE, "aggressive: зрадник"),
        ("схоже що все між нами",   False, Tone.DECEPTIVE,  "deceptive keywords"),
        ("...",                     False, Tone.NEUTRAL,    "short/unknown → neutral"),
        ("будь-яка фраза",          True,  Tone.DECEPTIVE,  "is_deceptive=True overrides"),
        # mood labels
        ("hostile",                 False, Tone.AGGRESSIVE, "mood: hostile → aggressive"),
        ("calm",                    False, Tone.FRIENDLY,   "mood: calm → friendly"),
        ("neutral",                 False, Tone.NEUTRAL,    "mood: neutral → neutral"),
        ("paranoid",                False, Tone.AGGRESSIVE, "mood: paranoid → aggressive"),
    ]

    print(f"  {'Text':40s}  {'Expected':12s}  {'Got':12s}")
    print(f"  {'-'*40}  {'-'*12}  {'-'*12}")
    for text, is_dec, expected, label in cases:
        got = classify_tone(text, is_deceptive=is_dec)
        ok = got == expected
        marker = PASS if ok else FAIL
        display = (text[:37] + "...") if len(text) > 40 else text
        print(f"  {marker} {display:40s}  {expected.value:12s}  {got.value:12s}  ({label})")
        if ok:
            global passed
            passed += 1
        else:
            global failed
            failed += 1


# ---------------------------------------------------------------------------
# Block 2 — Transition Matrix
# ---------------------------------------------------------------------------

def block_transition_matrix():
    from pipeline.talk_transition import MATRIX, sample_talk_outcome, Tone

    # All 16 combinations exist
    check("MATRIX has 16 combinations", len(MATRIX) == 16)

    # All distributions sum to 1.0
    all_sum = all(abs(sum(dist.values()) - 1.0) < 1e-9 for dist in MATRIX.values())
    check("all distributions sum to 1.0", all_sum)

    # Spot-checks: most likely outcome for key pairs
    print()
    print("  Dominant outcomes (200 samples each):\n")
    spot_checks = [
        (Tone.FRIENDLY,   Tone.FRIENDLY,   "trust_gain",  "friendly+friendly → trust"),
        (Tone.AGGRESSIVE, Tone.FRIENDLY,   "conflict",    "aggressive+friendly → conflict"),
        (Tone.AGGRESSIVE, Tone.AGGRESSIVE, "conflict",    "aggressive+aggressive → conflict"),
        (Tone.DECEPTIVE,  Tone.FRIENDLY,   "trust_gain",  "deceptive+friendly → trust (trap)"),
        (Tone.NEUTRAL,    Tone.NEUTRAL,    "neutral",     "neutral+neutral → neutral"),
    ]

    random.seed(10)
    for sp, li, expected_dominant, label in spot_checks:
        counts = Counter(sample_talk_outcome(sp, li) for _ in range(200))
        dominant = counts.most_common(1)[0][0]
        dist_str = "  ".join(f"{o}:{c}" for o, c in sorted(counts.items()))
        ok = dominant == expected_dominant
        marker = PASS if ok else FAIL
        print(f"  {marker} {label}")
        print(f"      {dist_str}")
        check(label, ok)


# ---------------------------------------------------------------------------
# Block 3 — Apply Outcome
# ---------------------------------------------------------------------------

def block_apply_outcome():
    from pipeline.talk_transition import apply_talk_outcome, OUTCOME_DELTAS, topic_tension_delta
    from pipeline.state_machine import AgentState

    base = AgentState(
        agent_id="listener",
        anger=0.3,
        interest=0.5,
        trust={"speaker": 0.5},
    )

    print(f"  Base state: anger={base.anger}  interest={base.interest}  trust[speaker]={base.trust['speaker']}\n")

    outcomes_to_test = ["trust_gain", "neutral", "misunderstanding", "conflict"]
    for outcome in outcomes_to_test:
        s = apply_talk_outcome(base, outcome, toward_agent="speaker")
        d = OUTCOME_DELTAS[outcome]
        t_delta = topic_tension_delta(outcome)
        print(f"  outcome={outcome:15s}  anger={s.anger:.3f}  interest={s.interest:.3f}  trust[speaker]={s.trust.get('speaker', base.trust['speaker']):.3f}  topic_tension_delta={t_delta:+.2f}")

    print()

    # trust_gain
    s_tg = apply_talk_outcome(base, "trust_gain", toward_agent="speaker")
    check("trust_gain: trust increased",   s_tg.trust["speaker"] > base.trust["speaker"])
    check("trust_gain: anger decreased",   s_tg.anger < base.anger)
    check("trust_gain: interest increased", s_tg.interest > base.interest)

    # conflict
    s_c = apply_talk_outcome(base, "conflict", toward_agent="speaker")
    check("conflict: trust decreased",  s_c.trust["speaker"] < base.trust["speaker"])
    check("conflict: anger increased",  s_c.anger > base.anger)

    # misunderstanding
    s_m = apply_talk_outcome(base, "misunderstanding", toward_agent="speaker")
    check("misunderstanding: anger increased", s_m.anger > base.anger)
    check("misunderstanding: trust decreased", s_m.trust["speaker"] < base.trust["speaker"])

    # unknown toward_agent — no trust crash
    s_u = apply_talk_outcome(base, "conflict", toward_agent="unknown_agent")
    check("unknown toward_agent: no KeyError", True)

    # tension deltas
    check("conflict has highest tension delta", topic_tension_delta("conflict") > topic_tension_delta("trust_gain"))
    check("trust_gain has negative tension delta", topic_tension_delta("trust_gain") < 0)


# ---------------------------------------------------------------------------
# Block 4 — Integration with dialog engine
# ---------------------------------------------------------------------------

def block_integration():
    from pipeline.state_machine import AgentState
    from pipeline.memory import AgentMemory
    from simulation.dialog_engine import generate_round_dialog_stepped

    agent_configs = [
        {
            "agent_id": "agent_a",
            "soul_md": "Тестова душа.",
            "states_md": AgentState(agent_id="agent_a", mood="hostile", anger=0.6, trust={"agent_b": 0.5, "agent_c": 0.5, "agent_d": 0.5}).to_md(),
            "memory_summary": {},
            "deception_tendency": 30,
            "cooperation_bias": 70,
            "total_rounds": 10,
            "visible_history": {},
            "dm_target": None,
        },
        {
            "agent_id": "agent_b",
            "soul_md": "Тестова душа.",
            "states_md": AgentState(agent_id="agent_b", mood="confident", anger=0.1, trust={"agent_a": 0.5, "agent_c": 0.5, "agent_d": 0.5}).to_md(),
            "memory_summary": {},
            "deception_tendency": 80,   # deceptive
            "cooperation_bias": 30,
            "total_rounds": 10,
            "visible_history": {},
            "dm_target": None,
        },
        {
            "agent_id": "agent_c",
            "soul_md": "Тестова душа.",
            "states_md": AgentState(agent_id="agent_c", mood="neutral", anger=0.2, trust={"agent_a": 0.5, "agent_b": 0.5, "agent_d": 0.5}).to_md(),
            "memory_summary": {},
            "deception_tendency": 50,
            "cooperation_bias": 50,
            "total_rounds": 10,
            "visible_history": {},
            "dm_target": None,
        },
        {
            "agent_id": "agent_d",
            "soul_md": "Тестова душа.",
            "states_md": AgentState(agent_id="agent_d", mood="calm", anger=0.0, trust={"agent_a": 0.5, "agent_b": 0.5, "agent_c": 0.5}).to_md(),
            "memory_summary": {},
            "deception_tendency": 20,
            "cooperation_bias": 80,
            "total_rounds": 10,
            "visible_history": {},
            "dm_target": None,
        },
    ]

    # Aggressive text → should produce conflict outcomes
    random.seed(42)
    with patch("simulation.dialog_engine._call", return_value="зрадник, заплатиш за це"):
        dialog = generate_round_dialog_stepped(
            round_number=1, agent_configs=agent_configs, steps_per_round=8
        )

    print(f"  messages (aggressive mock): {len(dialog.messages)}")
    print(f"  talk_signals: {dialog.talk_signals}")
    check("RoundDialog has talk_signals dict", isinstance(dialog.talk_signals, dict))
    check("talk_signals populated (at least 1 entry)", len(dialog.talk_signals) > 0)
    check("talk_signals values are valid signal strings", all(
        v in {"cooperative", "neutral", "threatening"}
        for v in dialog.talk_signals.values()
    ))

    # Aggressive text → mostly threatening signals
    threatening_count = sum(1 for v in dialog.talk_signals.values() if v == "threatening")
    print(f"  threatening signals: {threatening_count}/{len(dialog.talk_signals)}")
    check("aggressive text produces threatening signals", threatening_count > 0)

    # Friendly text → cooperative/neutral signals
    random.seed(42)
    with patch("simulation.dialog_engine._call", return_value="довіряю тобі, разом впораємось"):
        dialog2 = generate_round_dialog_stepped(
            round_number=2, agent_configs=agent_configs, steps_per_round=8
        )
    print(f"\n  messages (friendly mock): {len(dialog2.messages)}")
    print(f"  talk_signals: {dialog2.talk_signals}")
    non_threatening = sum(1 for v in dialog2.talk_signals.values() if v != "threatening")
    check("friendly text mostly non-threatening signals", non_threatening > 0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"\n{BOLD}Island — A-Level Smoke Test (Talk Transition){RESET}")
    print("=" * 55)

    run_block("[1] TONE CLASSIFICATION", block_tone_classification)
    run_block("[2] TRANSITION MATRIX", block_transition_matrix)
    run_block("[3] APPLY OUTCOME", block_apply_outcome)
    run_block("[4] INTEGRATION WITH DIALOG ENGINE", block_integration)

    total = passed + failed
    print()
    print("=" * 55)
    color = "\033[92m" if failed == 0 else "\033[91m"
    print(f"{BOLD}{color}=== SUMMARY: {passed}/{total} passed ==={RESET}")
    if failed > 0:
        print(f"  {failed} checks failed — see {FAIL} marks above.")
    print()
    sys.exit(0 if failed == 0 else 1)
