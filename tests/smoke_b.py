"""
smoke_b.py

B-level end-to-end smoke test for Island simulation.
Runs run_simulation with 4 synthetic agents, 3 rounds, mock LLM.

No disk I/O, no real LLM calls.

Usage:
    python3 tests/smoke_b.py
"""

import sys
import random
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
# Synthetic agent factory
# ---------------------------------------------------------------------------

def make_agents():
    from pipeline.state_machine import AgentState
    from pipeline.memory import AgentMemory
    from simulation.game_engine import SimAgent

    agent_ids = ["agent_a", "agent_b", "agent_c", "agent_d"]
    cores = [
        {"cooperation_bias": 70, "deception_tendency": 30, "strategic_horizon": 60, "risk_appetite": 50},
        {"cooperation_bias": 30, "deception_tendency": 80, "strategic_horizon": 70, "risk_appetite": 60},
        {"cooperation_bias": 50, "deception_tendency": 50, "strategic_horizon": 50, "risk_appetite": 50},
        {"cooperation_bias": 60, "deception_tendency": 40, "strategic_horizon": 80, "risk_appetite": 40},
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
        memory = AgentMemory(agent_id=aid)
        agents.append(SimAgent(
            agent_id=aid,
            soul_md=f"Soul of {aid}. Strategic. Observant.",
            core=cores[i],
            states=state,
            memory=memory,
        ))
    return agents


# ---------------------------------------------------------------------------
# Block 1 — Bootstrap
# ---------------------------------------------------------------------------

def block_bootstrap(agents):
    from simulation.game_engine import SimAgent
    from pipeline.state_machine import AgentState
    from pipeline.memory import AgentMemory

    print(f"  Agents created: {len(agents)}")
    for a in agents:
        coop = a.core.get("cooperation_bias", "?")
        dec = a.core.get("deception_tendency", "?")
        print(f"    {a.agent_id}  coop={coop}  deception={dec}  mood={a.states.mood}")

    check("4 agents created", len(agents) == 4)
    check("all agents have soul_md", all(a.soul_md for a in agents))
    check("all agents have states", all(isinstance(a.states, AgentState) for a in agents))
    check("all agents have memory", all(isinstance(a.memory, AgentMemory) for a in agents))
    check("trust initialized for all peers", all(
        len(a.states.trust) == 3 for a in agents
    ))


# ---------------------------------------------------------------------------
# Block 2 — Run Simulation
# ---------------------------------------------------------------------------

def block_run_simulation(agents):
    from simulation.game_engine import run_simulation

    print("  Running 3 rounds with mock LLM...")

    random.seed(99)
    with patch("simulation.dialog_engine._call", return_value="Тестова репліка від агента."):
        result = run_simulation(
            agents=agents,
            total_rounds=3,
            use_dialog=True,
            simulation_id="smoke_b_test",
        )

    print()
    print(f"  simulation_id: {result.simulation_id}")
    print(f"  rounds recorded: {len(result.rounds)}")
    print(f"  winner: {result.winner}")
    print()
    print("  Final scores:")
    for aid, score in sorted(result.final_scores.items(), key=lambda x: -x[1]):
        print(f"    {aid}: {score:+.2f}  {bar(max(0.0, score / 60.0))}")

    check("3 rounds recorded", len(result.rounds) == 3)
    check("all 4 agents in final_scores", len(result.final_scores) == 4)
    check("winner is one of the agents", result.winner in [a.agent_id for a in agents])
    check("action_log has 3 rounds", len(result.action_log) == 3)
    check("each round has actions for all agents", all(
        len(result.rounds[i].actions) == 4 for i in range(3)
    ))

    return result


# ---------------------------------------------------------------------------
# Block 3 — State Evolution
# ---------------------------------------------------------------------------

def block_state_evolution(agents, initial_states: dict):
    print("  State changes after 3 rounds:\n")
    print(f"  {'agent':12s}  {'mood':12s}  {'tension':22s}  {'anger':22s}")
    print(f"  {'-'*12}  {'-'*12}  {'-'*22}  {'-'*22}")

    changed_count = 0
    for a in agents:
        init = initial_states[a.agent_id]
        curr = a.states
        tension_changed = abs(curr.tension - init["tension"]) > 0.001
        anger_changed = abs(curr.anger - init["anger"]) > 0.001
        if tension_changed or anger_changed:
            changed_count += 1
        tension_str = f"{init['tension']:.3f} → {curr.tension:.3f}"
        anger_str   = f"{init['anger']:.3f} → {curr.anger:.3f}"
        print(f"  {a.agent_id:12s}  {curr.mood:12s}  {tension_str:22s}  {anger_str:22s}")

    print()
    check("at least 2 agents changed tension", changed_count >= 2)
    check("all agents have valid mood after 3 rounds", all(
        a.states.mood in {"neutral","calm","confident","dominant","uncertain","hostile","fearful","paranoid"}
        for a in agents
    ))
    check("round_number incremented to 3", all(a.states.round_number == 3 for a in agents))

    # Trust changed
    trust_changed = any(
        abs(a.states.trust.get(peer, 0.5) - 0.5) > 0.01
        for a in agents
        for peer in a.states.trust
    )
    check("trust values changed from initial 0.5", trust_changed)


# ---------------------------------------------------------------------------
# Block 4 — Memory Integrity
# ---------------------------------------------------------------------------

def block_memory(agents):
    for a in agents:
        rounds_recorded = len(a.memory.rounds)
        print(f"  {a.agent_id}: {rounds_recorded} rounds in memory")

    print()
    check("all agents have 3 rounds in memory", all(
        len(a.memory.rounds) == 3 for a in agents
    ))

    # Check dialog_heard populated (mock LLM returns text so messages exist)
    any_dialog = any(
        bool(r.dialog_heard)
        for a in agents
        for r in a.memory.rounds
    )
    check("at least one agent has dialog_heard populated", any_dialog)

    # Check payoff_delta recorded
    check("payoff_delta recorded in all rounds", all(
        isinstance(r.payoff_delta, float)
        for a in agents
        for r in a.memory.rounds
    ))

    # Check total_score accumulates
    check("total_score non-zero after 3 rounds", all(
        a.memory.total_score != 0 for a in agents
    ))

    # Summary structure
    s = agents[0].memory.summary()
    check("summary rounds_played = 3", s.get("rounds_played") == 3)


# ---------------------------------------------------------------------------
# Block 5 — DM in Dialog
# ---------------------------------------------------------------------------

def block_dm_dialog(result):
    # Check round 1 dialog
    round1 = result.rounds[0]
    dialog = round1.dialog

    if dialog is None:
        print(f"  {FAIL} No dialog in round 1")
        global failed
        failed += 1
        return

    pub = [m for m in dialog.messages if m.channel == "public"]
    dms = [m for m in dialog.messages if m.channel.startswith("dm_")]

    print(f"  Round 1 dialog:")
    print(f"    public messages:  {len(pub)}")
    print(f"    DM messages:      {len(dms)}")
    if dms:
        for dm in dms:
            print(f"    DM: {dm.sender_id} → {dm.channel}  \"{dm.text[:40]}\"")

    print()
    check("round 1 has public messages", len(pub) > 0)
    check("round 1 has at least 1 DM", len(dms) >= 1)
    check("DM channel format is dm_<id>", all(
        m.channel.startswith("dm_") and len(m.channel) > 3
        for m in dms
    ))
    check("DM text is non-empty", all(m.text.strip() for m in dms))

    # Check across all rounds
    total_dms = sum(
        len([m for m in r.dialog.messages if m.channel.startswith("dm_")])
        for r in result.rounds
        if r.dialog
    )
    print(f"  Total DMs across 3 rounds: {total_dms}")
    check("DMs present across multiple rounds", total_dms >= 3)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"\n{BOLD}Island — B-Level End-to-End Smoke Test{RESET}")
    print("=" * 50)

    # Build agents once, capture initial states
    agents = make_agents()
    initial_states = {
        a.agent_id: {"tension": a.states.tension, "anger": a.states.anger}
        for a in agents
    }

    result_holder = [None]

    def _block_bootstrap():
        block_bootstrap(agents)

    def _block_run():
        result_holder[0] = block_run_simulation(agents)

    def _block_states():
        if result_holder[0]:
            block_state_evolution(agents, initial_states)
        else:
            global failed
            print(f"  {FAIL} Skipped — simulation did not run")
            failed += 1

    def _block_memory():
        block_memory(agents)

    def _block_dm():
        if result_holder[0]:
            block_dm_dialog(result_holder[0])
        else:
            global failed
            print(f"  {FAIL} Skipped — simulation did not run")
            failed += 1

    run_block("[1] SIMULATION BOOTSTRAP", _block_bootstrap)
    run_block("[2] RUN SIMULATION (3 rounds, mock LLM)", _block_run)
    run_block("[3] STATE EVOLUTION", _block_states)
    run_block("[4] MEMORY INTEGRITY", _block_memory)
    run_block("[5] DM IN DIALOG", _block_dm)

    total = passed + failed
    print()
    print("=" * 50)
    color = "\033[92m" if failed == 0 else "\033[91m"
    print(f"{BOLD}{color}=== SUMMARY: {passed}/{total} passed ==={RESET}")
    if failed > 0:
        print(f"  {failed} checks failed — see {FAIL} marks above.")
    print()
    sys.exit(0 if failed == 0 else 1)
