"""
run_batch_250.py — 250 Island games, 4 random agents, 10 rounds each.

Usage:
    python run_batch_250.py                  # 250 games, 4 workers
    python run_batch_250.py --games 50       # quick test
    python run_batch_250.py --workers 2      # fewer parallel games
    python run_batch_250.py --no-progress    # no live table (CI/log mode)

Results saved to: logs/batch_results.json (updated after each game)
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ── load .env ──────────────────────────────────────────────────────────────────
_env = ROOT / ".env"
if _env.exists():
    for _line in _env.read_text(encoding="utf-8-sig").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            k, _, v = _line.partition("=")
            k, v = k.strip(), v.strip().strip("\"'")
            if k not in os.environ:
                os.environ[k] = v

# ── ANSI ───────────────────────────────────────────────────────────────────────
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RED    = "\033[91m"
PURPLE = "\033[95m"

# ── RESULTS FILE ───────────────────────────────────────────────────────────────
RESULTS_PATH = ROOT / "logs" / "batch_results.json"
RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── THREAD-SAFE STATS ──────────────────────────────────────────────────────────
_lock = threading.Lock()

stats: dict = {
    "total_games": 0,
    "completed": 0,
    "failed": 0,
    "started_at": datetime.now().isoformat(),
    "agents": {},   # agent_id → {wins, games, total_score, cooperations, betrayals}
    "games": [],    # list of compact game summaries
}


def _agent_stat(agent_id: str) -> dict:
    if agent_id not in stats["agents"]:
        stats["agents"][agent_id] = {
            "wins": 0, "games": 0,
            "total_score": 0.0,
            "cooperations": 0, "betrayals": 0,
        }
    return stats["agents"][agent_id]


def record_game(result, agent_names: dict) -> None:
    """Thread-safe: record one game result into global stats."""
    with _lock:
        winner = getattr(result, "winner", None)
        scores = getattr(result, "final_scores", {}) or {}
        rounds = getattr(result, "rounds", []) or []

        # Count coop/betray across all rounds
        coop_counts: dict[str, int] = defaultdict(int)
        betray_counts: dict[str, int] = defaultdict(int)
        for rnd in rounds:
            for src_id, acts in (rnd.actions or {}).items():
                for tgt_id, val in acts.items():
                    # val can be a float OR a dict {dim_id: value}
                    if isinstance(val, dict):
                        v = float(val.get("cooperation", 0.5))
                    elif isinstance(val, (int, float)):
                        v = float(val)
                    else:
                        v = 0.5
                    if v >= 0.66:
                        coop_counts[src_id] += 1
                    elif v <= 0.33:
                        betray_counts[src_id] += 1

        game_summary = {
            "game_num": stats["completed"] + 1,
            "agents": list(scores.keys()),
            "winner": winner,
            "scores": {k: round(v, 2) for k, v in scores.items()},
        }

        for aid, score in scores.items():
            s = _agent_stat(aid)
            s["games"] += 1
            s["total_score"] += score
            s["cooperations"] += coop_counts.get(aid, 0)
            s["betrayals"] += betray_counts.get(aid, 0)
            if aid == winner:
                s["wins"] += 1

        stats["completed"] += 1
        stats["games"].append(game_summary)

        # Persist after every game
        _save_results()


def _save_results() -> None:
    """Write stats to JSON (called inside lock)."""
    out = {**stats, "saved_at": datetime.now().isoformat()}
    RESULTS_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


# ── AGENT LOADING ──────────────────────────────────────────────────────────────
def load_roster() -> list[dict]:
    roster_path = ROOT / "agents" / "roster.json"
    if not roster_path.exists():
        print(f"{RED}ERROR: agents/roster.json not found{RESET}")
        sys.exit(1)
    return json.loads(roster_path.read_text(encoding="utf-8")).get("agents", [])


def build_agents_for_ids(selected_ids: list[str]):
    """Load fresh agent objects from disk for a specific subset."""
    from simulation.game_engine import load_agents_from_disk
    agents_dir = ROOT / "agents"
    return load_agents_from_disk(selected_ids, agents_dir)


# ── SINGLE GAME ────────────────────────────────────────────────────────────────
def run_one_game(game_num: int, agent_ids: list[str], total_rounds: int,
                 model: str, show_errors: bool = False) -> bool:
    """Run one simulation. Returns True on success."""
    try:
        agents = build_agents_for_ids(agent_ids)
        from simulation.game_engine import run_simulation

        result = run_simulation(
            agents=agents,
            total_rounds=total_rounds,
            model=model,
            use_dialog=False,   # skip dialog for speed
            verbose=False,
        )

        names = {a.agent_id: getattr(a, "name", a.agent_id[-8:]) for a in agents}
        record_game(result, names)
        return True

    except Exception as e:
        with _lock:
            stats["failed"] += 1
        if show_errors:
            print(f"  {RED}Game {game_num} failed: {e}{RESET}", flush=True)
        return False


# ── PROGRESS DISPLAY ───────────────────────────────────────────────────────────
def print_progress(total: int, roster: list[dict]) -> None:
    """Print live leaderboard table."""
    with _lock:
        done      = stats["completed"]
        failed    = stats["failed"]
        running   = total - done - failed
        elapsed   = time.time() - _start_time
        rate      = done / elapsed if elapsed > 0 else 0
        remaining = (total - done) / rate if rate > 0 else 0

        print(f"\n{BOLD}{'═'*62}{RESET}")
        print(f"{BOLD}  BATCH PROGRESS: {done}/{total} ✓   {failed} ✗   "
              f"~{remaining/60:.0f}м залишилось{RESET}")
        print(f"{'─'*62}")

        # Build name map
        name_map = {a["id"]: a.get("name", a["id"][-8:]) for a in roster}

        # Sort agents by win rate
        ag = [
            (aid, s) for aid, s in stats["agents"].items() if s["games"] > 0
        ]
        ag.sort(key=lambda x: x[1]["wins"] / x[1]["games"], reverse=True)

        print(f"  {'Агент':<16} {'Ігри':>5} {'Перем':>6} {'Win%':>6} "
              f"{'Avg↑':>7} {'Coop%':>7}")
        print(f"  {'─'*16} {'─'*5} {'─'*6} {'─'*6} {'─'*7} {'─'*7}")

        for aid, s in ag[:12]:  # top 12
            name = name_map.get(aid, aid[-8:])[:14]
            games = s["games"]
            wins  = s["wins"]
            win_p = wins / games * 100
            avg_s = s["total_score"] / games
            total_acts = s["cooperations"] + s["betrayals"]
            coop_p = s["cooperations"] / total_acts * 100 if total_acts > 0 else 0

            bar = GREEN if win_p > 20 else YELLOW if win_p > 10 else DIM
            print(f"  {bar}{name:<16}{RESET} {games:>5} {wins:>6} "
                  f"{bar}{win_p:>5.1f}%{RESET} {avg_s:>7.1f} {coop_p:>6.0f}%")

        print(f"{'═'*62}\n", flush=True)


# ── MAIN ───────────────────────────────────────────────────────────────────────
_start_time = time.time()


def main():
    global _start_time

    parser = argparse.ArgumentParser(description="Batch Island simulator — 250 games")
    parser.add_argument("--games",    type=int, default=250,   help="Total games (default 250)")
    parser.add_argument("--rounds",   type=int, default=10,    help="Rounds per game (default 10)")
    parser.add_argument("--workers",  type=int, default=4,     help="Parallel workers (default 4)")
    parser.add_argument("--model",    type=str, default="",    help="LLM model override")
    parser.add_argument("--agents-per-game", type=int, default=4, help="Agents per game (default 4)")
    parser.add_argument("--no-progress", action="store_true",  help="Suppress live table")
    args = parser.parse_args()

    model = args.model or os.environ.get("DEFAULT_MODEL", "google/gemini-2.0-flash-001")
    apg   = args.agents_per_game

    roster = load_roster()
    if len(roster) < apg:
        print(f"{RED}ERROR: need at least {apg} agents, have {len(roster)}{RESET}")
        sys.exit(1)

    all_ids = [a["id"] for a in roster]
    stats["total_games"] = args.games

    print(f"\n{BOLD}{'═'*62}{RESET}")
    print(f"{BOLD}{'ISLAND BATCH RUN':^62}{RESET}")
    print(f"{BOLD}{f'{args.games} games  ·  {apg} agents/game  ·  {args.rounds} rounds':^62}{RESET}")
    print(f"{BOLD}{f'{args.workers} workers  ·  model: {model}':^62}{RESET}")
    print(f"{BOLD}{'═'*62}{RESET}\n")
    print(f"  Results → {CYAN}{RESULTS_PATH}{RESET}\n", flush=True)

    # Build game queue: random 4-agent combos
    game_queue = []
    for i in range(args.games):
        selected = random.sample(all_ids, apg)
        game_queue.append((i + 1, selected))

    _start_time = time.time()
    progress_every = max(1, args.games // 25)  # print table ~25 times

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(run_one_game, gnum, aids, args.rounds, model): gnum
            for gnum, aids in game_queue
        }

        done_count = 0
        for fut in as_completed(futures):
            gnum = futures[fut]
            ok   = fut.result()

            done_count += 1
            status = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
            print(f"  {DIM}[{done_count:>3}/{args.games}]{RESET} гра {gnum:>3} {status}",
                  flush=True)

            if not args.no_progress and done_count % progress_every == 0:
                print_progress(args.games, roster)

    # Final table
    print_progress(args.games, roster)

    elapsed = time.time() - _start_time
    print(f"\n{GREEN}{BOLD}DONE! {stats['completed']} ігор за {elapsed/60:.1f} хв "
          f"({elapsed/max(stats['completed'],1):.1f}s/гра){RESET}")
    print(f"  Результати: {CYAN}{RESULTS_PATH}{RESET}\n")


if __name__ == "__main__":
    # Windows: force UTF-8 stdout
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    main()
