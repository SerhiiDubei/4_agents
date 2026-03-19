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
    parser.add_argument("--base-seconds", type=int, default=90, help="Starting time per player (seconds)")
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
        apply_mana_per_round,
        apply_code_use,
        run_storm,
        run_crisis,
        apply_game_end_bonuses,
        is_game_over,
        log_game_start,
        log_game_over,
        log_code_buy,
        build_situation_text,
        log_round_start,
        log_player_intent,
    )
    from game_modes.time_wars.agent_context import get_agent_action_mock
    from game_modes.time_wars.logging_export import write_session_log
    from game_modes.time_wars.shop import load_codes, get_available_codes, buy_code
    from game_modes.time_wars.log_to_html import generate_time_wars_html

    session_id = f"tw_{int(time.time())}"
    session = create_session(
        session_id=session_id,
        agent_ids=agent_ids,
        base_seconds_per_player=args.base_seconds,
        duration_limit_sec=args.duration,
    )
    log_game_start(session)

    codes_catalog = load_codes()
    if not codes_catalog:
        # Legacy: one code per player for testing if no codes.json
        for p in session.players:
            p.inventory.append({"code_id": "BONUS_30", "effect_type": "self_add", "seconds": 30})

    rng = random.Random(args.seed)
    action_interval = args.ticks_per_action
    min_ticks_before_elimination_win = 5 * action_interval
    storm_at = args.duration // 2
    crisis_at = 3 * args.duration // 4

    for t in range(1, args.duration + 1):
        eliminated = tick(session, t)
        if is_game_over(session, t, min_ticks_before_elimination_win):
            apply_game_end_bonuses(session, t)
            active = session.active_players()
            winner = active[0].agent_id if len(active) == 1 else None
            log_game_over(session, t, winner_id=winner)
            break
        if t % action_interval == 0:
            round_num = t // action_interval
            game_timer_sec = t
            log_round_start(
                session,
                round_num,
                t,
                game_timer_sec,
                build_situation_text(session),
            )
            apply_mana_per_round(session, t)
            # Shop phase (once per round): each player may buy one code from available
            if codes_catalog:
                for p in session.active_players():
                    available = get_available_codes(session, p.agent_id, codes_catalog)
                    if available and rng.random() < 0.25:
                        card = rng.choice(available)
                        if buy_code(session, p.agent_id, card["id"], codes_catalog):
                            log_code_buy(session, p.agent_id, card["id"], card.get("cost_mana", 0), t)
            for p in session.active_players():
                act = get_agent_action_mock(
                    session, p.agent_id, rng=rng,
                    round_num=round_num, total_rounds=max(20, args.duration // action_interval),
                    current_tick=t, ticks_per_action=action_interval,
                )
                log_player_intent(
                    session,
                    p.agent_id,
                    t,
                    thought=act.get("thought", ""),
                    plan=act.get("plan", ""),
                    choice=act.get("choice", ""),
                    reason=act.get("reason", ""),
                )
                if act["action"] == "cooperate" and act["target_id"]:
                    apply_cooperate(session, p.agent_id, act["target_id"], t)
                elif act["action"] == "steal" and act["target_id"]:
                    apply_steal(session, p.agent_id, act["target_id"], t, rng=rng)
                elif act["action"] == "use_code" and act["code_index"] is not None:
                    apply_code_use(session, p.agent_id, act["code_index"], t, rng=rng)
        if t == storm_at:
            run_storm(session, t, delta_sec=-15)
        if t == crisis_at:
            run_crisis(session, t, threshold_sec=80, penalty_sec=-15)
        if is_game_over(session, t, min_ticks_before_elimination_win):
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
    html_path = generate_time_wars_html(path)
    import webbrowser
    webbrowser.open(html_path.as_uri())
    print(f"Session {session_id} finished. Log: {path}")
    print(f"HTML (відкрито в браузері): {html_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
