"""
stress_rounds.py

Stress tests for Island simulation: many rounds and sequential games.
Uses mock LLM (no real API calls). No disk I/O.

- 25 rounds in one run: run_simulation with 25 rounds, then archive_game; check memory and trust_snapshot.
- Two sequential "games" in one process: run 3 rounds, archive_game, run 2 rounds, archive_game; check game_history length and trust_snapshot in both entries.

Usage:
    python tests/stress_rounds.py
"""

import sys
import random
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

PASS = "\033[92mOK\033[0m"
FAIL = "\033[91mFAIL\033[0m"
HEADER = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"

passed = 0
failed = 0


def check(label: str, condition: bool) -> bool:
    global passed, failed
    if condition:
        print(f"  {PASS} {label}")
        passed += 1
    else:
        print(f"  {FAIL} {label}")
        failed += 1
    return condition


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
            soul_md=f"Soul of {aid}.",
            core=cores[i],
            states=state,
            memory=memory,
        ))
    return agents


def mock_call_openrouter(*args, **kwargs):
    """Accept any call_openrouter args; return reasoning JSON or dialog text."""
    if kwargs.get("json_schema"):
        return '{"thought": "Stress test.", "intents": {"agent_a": 0.66, "agent_b": 0.66, "agent_c": 0.66, "agent_d": 0.66}}'
    return "Тестова репліка."


def run_with_mock(total_rounds: int, agents, simulation_id: str = "stress"):
    from simulation.game_engine import run_simulation
    with patch("simulation.dialog_engine._call", return_value="Тестова репліка."):
        with patch("pipeline.seed_generator.call_openrouter", side_effect=mock_call_openrouter):
            return run_simulation(
                agents=agents,
                total_rounds=total_rounds,
                use_dialog=True,
                simulation_id=simulation_id,
            )


def main():
    global passed, failed
    print(f"\n{HEADER}{BOLD}=== Stress: 25 rounds ==={RESET}\n")

    agents = make_agents()
    random.seed(42)
    result = run_with_mock(25, agents, "stress_25")
    check("25 rounds completed without exception", result is not None and len(result.rounds) == 25)
    check("all agents have 25 rounds in memory", all(len(a.memory.rounds) == 25 for a in agents))
    check("trust_history populated", all(len(a.memory.trust_history) >= 1 for a in agents))

    for a in agents:
        a.memory.archive_game("stress_game", result.winner, clear_rounds=True)
    gh_lens = [len(a.memory.game_history) for a in agents]
    # run_simulation may already call archive_game once; we call it again so expect >= 1
    check("archive_game: each agent has at least one game_history entry", all(n >= 1 for n in gh_lens))
    check("trust_snapshot present in last archived entry", all(
        a.memory.game_history and "trust_snapshot" in a.memory.game_history[-1] for a in agents
    ))
    check("trust_snapshot has peer keys", all(
        a.memory.game_history and len(a.memory.game_history[-1].get("trust_snapshot", {})) >= 1 for a in agents
    ))

    print(f"\n{HEADER}{BOLD}=== Stress: two sequential games ==={RESET}\n")

    agents2 = make_agents()
    random.seed(43)
    r1 = run_with_mock(3, agents2, "seq_1")
    check("first game 3 rounds", r1 is not None and len(r1.rounds) == 3)
    for a in agents2:
        a.memory.archive_game("game_1", r1.winner, clear_rounds=True)
    check("after first archive each agent has >= 1 game_history entry", all(len(a.memory.game_history) >= 1 for a in agents2))

    r2 = run_with_mock(2, agents2, "seq_2")
    check("second game 2 rounds", r2 is not None and len(r2.rounds) == 2)
    for a in agents2:
        a.memory.archive_game("game_2", r2.winner, clear_rounds=True)
    check("after second archive each agent has >= 2 game_history entries", all(len(a.memory.game_history) >= 2 for a in agents2))
    check("both first and last entries have trust_snapshot", all(
        len(a.memory.game_history) >= 2
        and "trust_snapshot" in a.memory.game_history[0]
        and "trust_snapshot" in a.memory.game_history[-1]
        for a in agents2
    ))

    print()
    total = passed + failed
    color = "\033[92m" if failed == 0 else "\033[91m"
    print(f"{BOLD}{color}=== Stress summary: {passed}/{total} passed ==={RESET}\n")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
