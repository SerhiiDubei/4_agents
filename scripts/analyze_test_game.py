"""
analyze_test_game.py

Prints a short report after a test game: log summary, agent MEMORY game_history,
conclusion, trust_snapshot, and narrative summary.

Usage:
  python scripts/analyze_test_game.py test_analysis
  python scripts/analyze_test_game.py test_analysis --agents-dir agents
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze results of a test game run.")
    parser.add_argument("name", type=str, nargs="?", default="test_analysis", help="Log name suffix (default: test_analysis)")
    parser.add_argument("--logs-dir", type=Path, default=None, help="Logs directory (default: ROOT/logs)")
    parser.add_argument("--agents-dir", type=Path, default=None, help="Agents directory (default: ROOT/agents)")
    args = parser.parse_args()

    logs_dir = args.logs_dir or ROOT / "logs"
    agents_dir = args.agents_dir or ROOT / "agents"

    pattern = f"game_*_{args.name}.json"
    candidates = sorted(logs_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        print(f"No log found: {logs_dir / pattern}", file=sys.stderr)
        return 1

    log_path = candidates[0]
    print(f"Log: {log_path}\n")
    with open(log_path, encoding="utf-8") as f:
        data = json.load(f)

    rounds = len(data.get("rounds", []))
    winner = data.get("winner", "")
    agent_ids = data.get("agent_ids", [])
    if not agent_ids and "rounds" in data and data["rounds"]:
        first_round = data["rounds"][0]
        agent_ids = list(first_round.get("actions", {}).keys())
    print(f"Rounds: {rounds}")
    print(f"Winner: {winner}")
    print(f"Agents: {agent_ids}\n")

    try:
        from pipeline.memory import memory_summary_to_narrative, AgentMemory
    except Exception as e:
        print(f"Import memory: {e}", file=sys.stderr)
        AgentMemory = None
        memory_summary_to_narrative = None

    names = {}
    roster_path = ROOT / "agents" / "roster.json"
    if roster_path.exists():
        roster = json.loads(roster_path.read_text(encoding="utf-8"))
        for a in roster.get("agents", []):
            if a.get("id") in agent_ids:
                names[a["id"]] = a.get("name", a["id"])

    for aid in agent_ids[:6]:
        mem_path = agents_dir / aid / "MEMORY.json"
        if not mem_path.exists():
            print(f"  [{aid}] MEMORY.json not found")
            continue
        with open(mem_path, encoding="utf-8") as f:
            mem_dict = json.load(f)
        gh = mem_dict.get("game_history", [])
        print(f"  [{names.get(aid, aid)}] game_history: {len(gh)} entries")
        if gh:
            last = gh[-1]
            concl = last.get("conclusion", "")
            snap = last.get("trust_snapshot", {})
            print(f"      conclusion: {'(set)' if concl else '(empty)'} {concl[:80]}{'...' if len(concl) > 80 else ''}")
            print(f"      trust_snapshot: {list(snap.keys())} -> {snap}")
        if AgentMemory and memory_summary_to_narrative:
            mem = AgentMemory.from_dict(mem_dict)
            narrative = memory_summary_to_narrative(mem.summary(), aid, names)
            print(f"      narrative: {narrative[:250]}{'...' if len(narrative) > 250 else ''}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
