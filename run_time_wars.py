"""
run_time_wars.py

Run one TIME WARS session: time as resource, ADD/Steal/Cooperate, roles with skills.
Uses roster for agent list; does not modify run_simulation_live or core game engine.
Logs to logs/time_wars_<session_id>_<timestamp>.jsonl.

Usage:
  python run_time_wars.py
  python run_time_wars.py --duration 120 --agents agent_synth_g,agent_synth_c
  python run_time_wars.py --duration 60 --ticks-per-action 10
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def load_roster_agents(selected_ids: list[str] | None = None) -> list[str]:
    """Load agent IDs from roster; if selected_ids given, filter to those."""
    roster_path = ROOT / "agents" / "roster.json"
    if not roster_path.exists():
        return selected_ids or ["agent_1", "agent_2", "agent_3", "agent_4"]
    import json
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    agents = roster.get("agents", [])
    all_ids = [a["id"] for a in agents]
    default_count = roster.get("default_count", 4)
    if not selected_ids:
        selected_ids = all_ids[:default_count]
    return [aid for aid in selected_ids if aid in all_ids] or all_ids[:default_count]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TIME WARS session (time pool, roles, cooperate/steal).")
    parser.add_argument("--duration", type=int, default=120, help="Game duration in seconds (simulated ticks)")
    parser.add_argument("--agents", type=str, default="", help="Comma-separated agent IDs (default: from roster)")
    parser.add_argument("--roles-file", type=Path, default=None, help="Path to roles.json (default: game_modes/time_wars/roles.json)")
    parser.add_argument("--ticks-per-action", type=int, default=15, help="Run action phase every N ticks")
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    parser.add_argument("--log-dir", type=Path, default=None, help="Log directory (default: ROOT/logs)")
    args = parser.parse_args()

    agent_ids = load_roster_agents(
        [x.strip() for x in args.agents.split(",") if x.strip()] if args.agents else None
    )
    if args.seed is not None:
        random.seed(args.seed)

    from game_modes.time_wars.state import create_session
    from game_modes.time_wars.loop import (
        tick,
        apply_cooperate,
        apply_steal,
        apply_code_use,
        run_storm,
        run_crisis,
        apply_game_end_bonuses,
        is_game_over,
        log_game_start,
        log_game_over,
    )
    from game_modes.time_wars.agent_context import get_agent_action_mock
    from game_modes.time_wars.logging_export import write_session_log

    session_id = f"tw_{int(time.time())}"
    session = create_session(
        session_id=session_id,
        agent_ids=agent_ids,
        base_seconds_per_player=min(300, args.duration),
        duration_limit_sec=args.duration,
    )
    log_game_start(session)

    # Spawn one code per player for testing
    for p in session.players:
        p.inventory.append({"code_id": "BONUS_30", "effect_type": "self_add", "seconds": 30})

    rng = random.Random(args.seed)
    action_interval = args.ticks_per_action
    storm_at = args.duration // 3
    crisis_at = 2 * args.duration // 3

    for t in range(1, args.duration + 1):
        eliminated = tick(session, t)
        if is_game_over(session, t):
            apply_game_end_bonuses(session, t)
            active = session.active_players()
            winner = active[0].agent_id if len(active) == 1 else None
            log_game_over(session, t, winner_id=winner)
            break
        if t % action_interval == 0:
            for p in session.active_players():
                act = get_agent_action_mock(session, p.agent_id, rng=rng)
                if act["action"] == "cooperate" and act["target_id"]:
                    apply_cooperate(session, p.agent_id, act["target_id"], t)
                elif act["action"] == "steal" and act["target_id"]:
                    apply_steal(session, p.agent_id, act["target_id"], t, rng=rng)
                elif act["action"] == "use_code" and act["code_index"] is not None:
                    apply_code_use(session, p.agent_id, act["code_index"], t)
        if t == storm_at:
            run_storm(session, t)
        if t == crisis_at:
            run_crisis(session, t, threshold_sec=60, penalty_sec=-30)
        if is_game_over(session, t):
            apply_game_end_bonuses(session, t)
            active = session.active_players()
            winner = active[0].agent_id if len(active) == 1 else None
            log_game_over(session, t, winner_id=winner)
            break
    else:
        apply_game_end_bonuses(session, args.duration)
        active = session.active_players()
        winner = max(active, key=lambda x: x.time_remaining_sec).agent_id if active else None
        log_game_over(session, args.duration, winner_id=winner)

    log_dir = args.log_dir or ROOT / "logs"
    path = write_session_log(session, log_dir)
    print(f"Session {session_id} finished. Log: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
