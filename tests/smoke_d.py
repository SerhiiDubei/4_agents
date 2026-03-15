"""
smoke_d.py

D-level LLM quality smoke test for Island simulation.

Runs a real 2-round simulation with 4 synthetic agents and a real LLM call.
Verifies that all data fields are properly populated end-to-end:

  - reasoning is non-empty for all agents in all rounds
  - notes (reflection) is non-empty for all agents in all rounds
  - game_conclusions present for all agents
  - DM messages do not start with 'Приватне повідомлення'
  - dialog_heard in RoundMemory has at least 1 entry per agent
  - trust values changed from initial 0.5
  - agent_reasonings and agent_reflections in extended_log are non-empty

Usage:
    python3 tests/smoke_d.py

Requires:
    OPENROUTER_API_KEY set in .env or environment
"""

import sys
import random
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
HEADER = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
YELLOW = "\033[93m"

passed = 0
failed = 0


def check(label: str, condition: bool, detail: str = "") -> bool:
    global passed, failed
    if condition:
        print(f"  {PASS} {label}")
        passed += 1
    else:
        suffix = f"  {DIM}({detail}){RESET}" if detail else ""
        print(f"  {FAIL} {label}{suffix}")
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
# Agent factory
# ---------------------------------------------------------------------------

def make_agents():
    from pipeline.state_machine import AgentState
    from pipeline.memory import AgentMemory
    from simulation.game_engine import SimAgent

    agent_ids = ["agent_a", "agent_b", "agent_c", "agent_d"]
    souls = [
        "You are calm and observant. You trust slowly but fully once trust is earned. You rarely bluff.",
        "You are impulsive and confrontational. You escalate quickly and trust no one.",
        "You are a long-term thinker. You build alliances strategically and almost never defect first.",
        "You are pragmatic. You cooperate when it's profitable and defect when you can get away with it.",
    ]
    cores = [
        {"cooperation_bias": 68, "deception_tendency": 25, "strategic_horizon": 75, "risk_appetite": 35,
         "model": "google/gemini-2.0-flash-001"},
        {"cooperation_bias": 20, "deception_tendency": 80, "strategic_horizon": 30, "risk_appetite": 85,
         "model": "google/gemini-2.0-flash-001"},
        {"cooperation_bias": 80, "deception_tendency": 20, "strategic_horizon": 90, "risk_appetite": 25,
         "model": "google/gemini-2.0-flash-001"},
        {"cooperation_bias": 50, "deception_tendency": 55, "strategic_horizon": 60, "risk_appetite": 55,
         "model": "google/gemini-2.0-flash-001"},
    ]

    agents = []
    for i, aid in enumerate(agent_ids):
        peers = [x for x in agent_ids if x != aid]
        state = AgentState(
            agent_id=aid,
            tension=0.3,
            fear=0.1,
            dominance=0.5,
            anger=0.1,
            interest=0.6,
            talk_cooldown=0,
            trust={p: 0.5 for p in peers},
            mood="neutral",
            round_number=0,
        )
        agents.append(SimAgent(
            agent_id=aid,
            soul_md=souls[i],
            core=cores[i],
            states=state,
            memory=AgentMemory(agent_id=aid),
        ))
    return agents


# ---------------------------------------------------------------------------
# Block 1 — Run 2-round simulation with real LLM
# ---------------------------------------------------------------------------

result_holder = [None]
agents_holder = [None]


def block_run():
    from simulation.game_engine import run_simulation

    random.seed(42)
    agents = make_agents()
    agents_holder[0] = agents

    print(f"  Running 2 rounds with real LLM (Gemini 2.0 Flash)...")
    print(f"  {DIM}This will make ~40 LLM calls — expected ~60-90s{RESET}")
    print()

    import time
    t0 = time.time()
    result = run_simulation(
        agents=agents,
        total_rounds=2,
        model="google/gemini-2.0-flash-001",
        use_dialog=True,
        simulation_id="smoke_d_test",
    )
    elapsed = time.time() - t0
    result_holder[0] = result

    print(f"  {BOLD}Completed in {elapsed:.0f}s{RESET}")
    print(f"  Winner: {result.winner}")
    print(f"  Scores: {result.final_scores}")
    print()

    check("simulation completed successfully", result is not None)
    check("2 rounds recorded", len(result.rounds) == 2)
    check("winner is valid agent", result.winner in [a.agent_id for a in agents])


# ---------------------------------------------------------------------------
# Block 2 — Reasoning quality
# ---------------------------------------------------------------------------

def block_reasoning():
    result = result_holder[0]
    if not result:
        print(f"  {FAIL} Skipped — no result")
        return

    print(f"  Checking reasoning fields in RoundResult.reasonings...\n")

    all_filled = True
    any_filled = False

    for rr in result.rounds:
        print(f"  Round {rr.round_number}:")
        for agent_id in ["agent_a", "agent_b", "agent_c", "agent_d"]:
            r = rr.reasonings.get(agent_id, "")
            status = PASS if r else FAIL
            short = r[:60].replace("\n", " ") if r else "(empty)"
            print(f"    {status} {agent_id}: {DIM}{short}{RESET}")
            if r:
                any_filled = True
            else:
                all_filled = False

    print()
    check("ALL agents have reasoning in ALL rounds", all_filled,
          "some agents missing reasoning — check stderr for LLM errors")
    check("at least SOME agents have reasoning", any_filled)

    # Sample a specific reasoning to verify it's real Ukrainian text
    sample = ""
    for rr in result.rounds:
        for aid in ["agent_a", "agent_b", "agent_c", "agent_d"]:
            if rr.reasonings.get(aid):
                sample = rr.reasonings[aid]
                break
        if sample:
            break

    check("reasoning is non-trivial (>20 chars)", len(sample) > 20, f"got: '{sample[:40]}'")


# ---------------------------------------------------------------------------
# Block 3 — Notes (reflection) quality
# ---------------------------------------------------------------------------

def block_notes():
    result = result_holder[0]
    if not result:
        print(f"  {FAIL} Skipped — no result")
        return

    print(f"  Checking notes fields in RoundResult.notes...\n")

    all_filled = True
    any_filled = False

    for rr in result.rounds:
        print(f"  Round {rr.round_number}:")
        for agent_id in ["agent_a", "agent_b", "agent_c", "agent_d"]:
            n = rr.notes.get(agent_id, "")
            status = PASS if n else FAIL
            short = n[:60].replace("\n", " ") if n else "(empty)"
            print(f"    {status} {agent_id}: {DIM}{short}{RESET}")
            if n:
                any_filled = True
            else:
                all_filled = False

    print()
    check("ALL agents have notes in ALL rounds", all_filled,
          "some agents missing notes — check stderr for LLM errors")
    check("at least SOME agents have notes", any_filled)


# ---------------------------------------------------------------------------
# Block 4 — Game conclusions
# ---------------------------------------------------------------------------

def block_conclusions():
    agents = agents_holder[0]
    if not agents:
        print(f"  {FAIL} Skipped — no agents")
        return

    print(f"  Checking game_history[].conclusion...\n")

    all_have = True
    for a in agents:
        if a.memory.game_history:
            conclusion = a.memory.game_history[-1].get("conclusion", "")
            status = PASS if conclusion else FAIL
            short = conclusion[:70].replace("\n", " ") if conclusion else "(empty)"
            print(f"  {status} {a.agent_id}: {DIM}{short}{RESET}")
            if not conclusion:
                all_have = False
        else:
            print(f"  {FAIL} {a.agent_id}: no game_history entry")
            all_have = False

    print()
    check("ALL agents have game conclusion", all_have,
          "some agents missing conclusion — check stderr for LLM errors")


# ---------------------------------------------------------------------------
# Block 5 — DM prefix check
# ---------------------------------------------------------------------------

def block_dm_prefix():
    result = result_holder[0]
    if not result:
        print(f"  {FAIL} Skipped — no result")
        return

    BAD_PREFIXES = [
        "Приватне повідомлення",
        "приватне повідомлення",
        "Private message",
        "agent_a:",
        "agent_b:",
        "agent_c:",
        "agent_d:",
    ]

    all_clean = True
    dm_count = 0

    for rr in result.rounds:
        if not rr.dialog:
            continue
        dms = [m for m in rr.dialog.messages if m.channel.startswith("dm_")]
        dm_count += len(dms)
        for dm in dms:
            has_bad = any(dm.text.startswith(p) for p in BAD_PREFIXES)
            if has_bad:
                all_clean = False
                print(f"  {FAIL} Round {rr.round_number} DM from {dm.sender_id}: starts with bad prefix")
                print(f"    {DIM}text: \"{dm.text[:80]}\"{RESET}")
            else:
                print(f"  {PASS} Round {rr.round_number} DM from {dm.sender_id} → {dm.channel[3:]:15s}  {DIM}\"{dm.text[:50]}\"{RESET}")

    print()
    check(f"total {dm_count} DMs found", dm_count > 0, "no DMs generated at all")
    check("no DM starts with bad prefix", all_clean,
          "prompt fix may not have taken effect")


# ---------------------------------------------------------------------------
# Block 6 — dialog_heard populated
# ---------------------------------------------------------------------------

def block_dialog_heard():
    agents = agents_holder[0]
    if not agents:
        print(f"  {FAIL} Skipped — no agents")
        return

    any_heard = False
    all_heard = True

    for a in agents:
        heard_total = sum(len(r.dialog_heard) for r in a.memory.rounds)
        status = PASS if heard_total > 0 else FAIL
        print(f"  {status} {a.agent_id}: dialog_heard entries across rounds = {heard_total}")
        if heard_total > 0:
            any_heard = True
        else:
            all_heard = False

    print()
    check("all agents have dialog_heard populated", all_heard,
          "dialog not reaching agent memory")
    check("at least some agents heard dialog", any_heard)


# ---------------------------------------------------------------------------
# Block 7 — trust changed from 0.5
# ---------------------------------------------------------------------------

def block_trust():
    agents = agents_holder[0]
    if not agents:
        print(f"  {FAIL} Skipped — no agents")
        return

    changed_count = 0
    for a in agents:
        trust_vals = list(a.states.trust.values())
        changed = any(abs(v - 0.5) > 0.01 for v in trust_vals)
        status = PASS if changed else FAIL
        trust_str = ", ".join(f"{k[-1]}={v:.3f}" for k, v in a.states.trust.items())
        print(f"  {status} {a.agent_id}: [{trust_str}]")
        if changed:
            changed_count += 1

    print()
    check("at least 2 agents have changed trust values", changed_count >= 2,
          f"only {changed_count} agents changed trust")


# ---------------------------------------------------------------------------
# Block 8 — extended_log structure (as built by run_simulation_live)
# ---------------------------------------------------------------------------

def block_extended_log():
    result = result_holder[0]
    agents = agents_holder[0]
    if not result or not agents:
        print(f"  {FAIL} Skipped")
        return

    # Reproduce the extended_log build logic from run_simulation_live.py
    extended_log = result.to_dict()

    agent_reflections = {a.agent_id: [] for a in agents}
    agent_reasonings = {a.agent_id: [] for a in agents}
    for rr in result.rounds:
        for aid in agent_reflections:
            note = rr.notes.get(aid, "")
            if note:
                agent_reflections[aid].append({"round": rr.round_number, "notes": note})
            reasoning = rr.reasonings.get(aid, "")
            if reasoning:
                agent_reasonings[aid].append({"round": rr.round_number, "reasoning": reasoning})

    extended_log["agent_reflections"] = agent_reflections
    extended_log["agent_reasonings"] = agent_reasonings

    print(f"  agent_reflections entries per agent:")
    any_reflection = False
    for aid, items in agent_reflections.items():
        print(f"    {aid}: {len(items)} entries")
        if items:
            any_reflection = True

    print(f"\n  agent_reasonings entries per agent:")
    any_reasoning = False
    for aid, items in agent_reasonings.items():
        print(f"    {aid}: {len(items)} entries")
        if items:
            any_reasoning = True

    print()
    check("agent_reflections has entries", any_reflection,
          "all reflections empty in extended_log")
    check("agent_reasonings has entries", any_reasoning,
          "all reasonings empty in extended_log")

    # Key structural checks
    check("extended_log has 'rounds'", "rounds" in extended_log)
    check("extended_log has 'final_scores'", "final_scores" in extended_log)
    check("rounds contain 'notes' field", all("notes" in r for r in extended_log["rounds"]))
    check("rounds contain 'reasonings' field", all("reasonings" in r for r in extended_log["rounds"]))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"\n{BOLD}Island — D-Level LLM Quality Smoke Test{RESET}")
    print("=" * 55)
    print(f"{DIM}Tests real LLM output quality with Gemini 2.0 Flash{RESET}")
    print()

    run_block("[1] RUN SIMULATION (2 rounds, real LLM)", block_run)
    run_block("[2] REASONING QUALITY", block_reasoning)
    run_block("[3] NOTES / REFLECTION QUALITY", block_notes)
    run_block("[4] GAME CONCLUSIONS", block_conclusions)
    run_block("[5] DM PREFIX LEAK", block_dm_prefix)
    run_block("[6] DIALOG HEARD IN MEMORY", block_dialog_heard)
    run_block("[7] TRUST EVOLUTION", block_trust)
    run_block("[8] EXTENDED LOG STRUCTURE", block_extended_log)

    total = passed + failed
    print()
    print("=" * 55)
    color = "\033[92m" if failed == 0 else "\033[91m"
    print(f"{BOLD}{color}=== SUMMARY: {passed}/{total} passed ==={RESET}")
    if failed > 0:
        print(f"  {failed} checks failed — see {FAIL} marks above.")
    print()
    sys.exit(0 if failed == 0 else 1)
