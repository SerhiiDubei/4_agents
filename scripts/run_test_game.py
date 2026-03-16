"""
run_test_game.py

Runs one short game with real LLM for system analysis.
Thin wrapper around run_simulation_live.py.

Usage:
  python scripts/run_test_game.py
  python scripts/run_test_game.py --rounds 5 --name my_test
  python scripts/run_test_game.py --rounds 3 --agents agent_synth_c,agent_synth_d
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one test game for analysis (calls run_simulation_live).")
    parser.add_argument("--rounds", type=int, default=3, help="Number of rounds (default: 3)")
    parser.add_argument("--name", type=str, default="test_analysis", help="Log name suffix (default: test_analysis)")
    parser.add_argument(
        "--agents",
        type=str,
        default="",
        help="Comma-separated agent IDs (default: from roster)",
    )
    parser.add_argument("--html", action="store_true", default=True, help="Export HTML/JSON log (default: True)")
    parser.add_argument("--no-html", action="store_false", dest="html", help="Disable HTML/JSON export")
    args = parser.parse_args()

    argv = [
        sys.executable,
        str(ROOT / "run_simulation_live.py"),
        "--rounds",
        str(args.rounds),
        "--name",
        args.name,
    ]
    if args.html:
        argv.append("--html")
    if args.agents:
        argv.extend(["--agents", args.agents])

    ret = subprocess.run(argv, cwd=ROOT)
    if ret.returncode == 0:
        logs_dir = ROOT / "logs"
        print(f"\nLogs: {logs_dir}")
        print(f"  Look for: game_*_{args.name}.json and game_*_{args.name}.html")
        print(f"  Analyze:  python scripts/analyze_test_game.py {args.name}\n")
    return ret.returncode


if __name__ == "__main__":
    sys.exit(main())
