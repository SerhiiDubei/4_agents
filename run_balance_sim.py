"""
Run TIME WARS balance simulator (no agents, math model only).

Usage:
  python run_balance_sim.py --grid --runs 1000
  python run_balance_sim.py --runs 500 --B 25 --T 20 --out balance_out.json
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from game_modes.time_wars.balance_sim import main

if __name__ == "__main__":
    sys.exit(main())
