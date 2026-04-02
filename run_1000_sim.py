"""
run_1000_sim.py — 1000 ігор Time Wars з mock-агентами + HTML візуалізація.

Usage:
    python run_1000_sim.py
    python run_1000_sim.py --runs 1000 --seed 42 --out sim_results.json
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import time
import webbrowser
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent

import sys
sys.path.insert(0, str(ROOT))

from game_modes.time_wars.state import create_session
from game_modes.time_wars.loop import (
    tick,
    apply_cooperate,
    apply_steal,
    apply_mana_per_round,
    escalating_drain,
    is_game_over,
    apply_game_end_bonuses,
    run_storm,
    run_code_phase,
)
from game_modes.time_wars.shop import load_codes, get_available_codes, buy_code, effective_cost
from game_modes.time_wars.agent_context import get_agent_action_mock

BASE_SEC = 1000
DRAIN_DOUBLE_EVERY = 50
DRAIN_BASE = 3
TICKS_PER_ACTION = 10
DURATION = 5_000
STORM_AFTER_TICKS = 300

AGENTS = [
    "agent_synth_g",
    "agent_synth_c",
    "agent_synth_d",
    "agent_synth_h",
    "agent_synth_i",
    "agent_synth_j",
]

ROLE_LABELS = {
    "role_snake": "Змій",
    "role_peacekeeper": "Миротворець",
    "role_banker": "Банкір",
    "role_gambler": "Авантюрист",
}


def run_one_game(run_id: int, rng: random.Random, codes_catalog: List[dict]) -> dict:
    session = create_session(
        session_id=f"sim_{run_id}",
        agent_ids=AGENTS,
        base_seconds_per_player=BASE_SEC,
        duration_limit_sec=DURATION,
    )

    role_map = {p.agent_id: p.role_id for p in session.players}
    action_counts: Dict[str, Counter] = {aid: Counter() for aid in AGENTS}
    elimination_order: List[dict] = []  # {agent_id, role_id, tick, round}
    rounds_played = 0
    final_tick = 0
    drain_history: List[dict] = []  # {round, tick, drain}

    for t in range(1, DURATION + 1):
        drain = escalating_drain(t, base=DRAIN_BASE, double_every=DRAIN_DOUBLE_EVERY)
        eliminated_this_tick = tick(session, t, drain_sec=drain)
        for aid in eliminated_this_tick:
            if not any(e["agent_id"] == aid for e in elimination_order):
                elimination_order.append({
                    "agent_id": aid,
                    "role_id": role_map.get(aid, ""),
                    "tick": t,
                    "round": rounds_played,
                })

        if is_game_over(session, t, TICKS_PER_ACTION):
            apply_game_end_bonuses(session, t)
            final_tick = t
            break

        if t % TICKS_PER_ACTION == 0:
            rounds_played += 1
            drain_history.append({"round": rounds_played, "tick": t, "drain": drain})
            apply_mana_per_round(session, t)

            # SHOP phase: buy as many codes as mana allows (mock: prefer situationally)
            if codes_catalog:
                for p in session.active_players():
                    bought = 0
                    while bought < 6:
                        available = get_available_codes(session, p.agent_id, codes_catalog)
                        if not available:
                            break
                        my_ratio = p.time_remaining_sec / BASE_SEC
                        if my_ratio < 0.4:
                            pref = [c for c in available if c.get("type") in ("self", "steal", "gamble")]
                        elif my_ratio > 0.7:
                            pref = [c for c in available if c.get("type") in ("give", "plus_all_except_one", "steal")]
                        else:
                            pref = []
                        card = rng.choice(pref) if pref else rng.choice(available)
                        cost = effective_cost(card, session, p.agent_id)
                        if p.mana < cost:
                            break
                        if buy_code(session, p.agent_id, card["id"], codes_catalog):
                            bought += 1
                        else:
                            break

            # CODE phase: utility-based code usage (separate from ACTION)
            run_code_phase(session, t, rng=rng)

            # Mock COMM phase: update trust slightly based on time pressure
            # (in real games this is LLM dialog; here we simulate trust drift)
            for p in session.active_players():
                my_ratio = p.time_remaining_sec / BASE_SEC
                for o in session.active_players():
                    if o.agent_id == p.agent_id:
                        continue
                    old_trust = session.get_trust(p.agent_id, o.agent_id)
                    # Desperate players trust slightly less (survival instinct)
                    drift = -0.02 if my_ratio < 0.3 else 0.0
                    session.set_trust(p.agent_id, o.agent_id, max(0.0, min(1.0, old_trust + drift)))

            # ACTION phase: per-target cooperation levels + cooperate/steal/pass
            for p in session.active_players():
                act = get_agent_action_mock(
                    session, p.agent_id, rng=rng,
                    round_num=rounds_played, total_rounds=max(20, DURATION // TICKS_PER_ACTION),
                    current_tick=t, ticks_per_action=TICKS_PER_ACTION,
                )
                action_counts[p.agent_id][act["action"]] += 1

                if act["action"] == "cooperate" and act["target_id"]:
                    apply_cooperate(session, p.agent_id, act["target_id"], t)
                elif act["action"] == "steal" and act["target_id"]:
                    apply_steal(session, p.agent_id, act["target_id"], t, rng=rng)

            if is_game_over(session, t, TICKS_PER_ACTION):
                apply_game_end_bonuses(session, t)
                final_tick = t
                break

        if t == STORM_AFTER_TICKS:
            run_storm(session, t, delta_sec=-20)
    else:
        final_tick = DURATION

    active = session.active_players()
    if len(active) == 1:
        winner_id = active[0].agent_id
    elif len(active) == 0:
        winner_id = max(session.players, key=lambda p: p.mana).agent_id
    else:
        winner_id = None

    winner_time = next((p.time_remaining_sec for p in session.players if p.agent_id == winner_id), 0)

    players_result = []
    for p in session.players:
        elim_info = next((e for e in elimination_order if e["agent_id"] == p.agent_id), None)
        if p.agent_id == winner_id:
            place = 1
        elif elim_info:
            idx = next(i for i, e in enumerate(elimination_order) if e["agent_id"] == p.agent_id)
            place = len(AGENTS) - idx
        else:
            place = len(AGENTS)

        players_result.append({
            "agent_id": p.agent_id,
            "role_id": p.role_id,
            "final_time_sec": p.time_remaining_sec,
            "place": place,
            "won": p.agent_id == winner_id,
            "actions": dict(action_counts[p.agent_id]),
            "elim_tick": elim_info["tick"] if elim_info else final_tick,
            "elim_round": elim_info["round"] if elim_info else rounds_played,
        })

    return {
        "run_id": run_id,
        "rounds": rounds_played,
        "final_tick": final_tick,
        "winner_id": winner_id,
        "winner_role": role_map.get(winner_id) if winner_id else None,
        "winner_time": winner_time,
        "elimination_order": elimination_order,
        "players": players_result,
        "drain_history": drain_history,
    }


def aggregate(results: List[dict]) -> dict:
    n = len(results)

    wins_per_role: Counter = Counter()
    games_per_role: Counter = Counter()
    for r in results:
        if r["winner_role"]:
            wins_per_role[r["winner_role"]] += 1
        for p in r["players"]:
            games_per_role[p["role_id"]] += 1

    win_rate_per_role = {
        role: wins_per_role.get(role, 0) / max(games_per_role.get(role, 1), 1)
        for role in games_per_role
    }

    rounds_list = [r["rounds"] for r in results]
    ticks_list = [r["final_tick"] for r in results]
    winner_times = [r["winner_time"] for r in results if r["winner_id"]]

    no_winner_count = sum(1 for r in results if not r["winner_id"])

    role_actions: Dict[str, Counter] = defaultdict(Counter)
    role_places: Dict[str, List[int]] = defaultdict(list)
    role_elim_rounds: Dict[str, List[int]] = defaultdict(list)
    role_elim_ticks: Dict[str, List[int]] = defaultdict(list)

    for r in results:
        for p in r["players"]:
            role_id = p["role_id"]
            for action, cnt in p["actions"].items():
                role_actions[role_id][action] += cnt
            role_places[role_id].append(p["place"])
            if not p["won"]:
                role_elim_rounds[role_id].append(p["elim_round"])
                role_elim_ticks[role_id].append(p["elim_tick"])

    role_action_pct = {}
    for role, ctr in role_actions.items():
        total = sum(ctr.values())
        role_action_pct[role] = {a: round(c / total * 100, 1) if total else 0 for a, c in ctr.items()}

    role_avg_place = {role: round(statistics.mean(places), 2) for role, places in role_places.items()}
    role_avg_elim_round = {role: round(statistics.mean(rds), 2) for role, rds in role_elim_rounds.items() if rds}
    role_avg_elim_tick = {role: round(statistics.mean(ts), 1) for role, ts in role_elim_ticks.items() if ts}

    first_elim_role: Counter = Counter()
    for r in results:
        if r["elimination_order"]:
            first_out = r["elimination_order"][0]
            first_elim_role[first_out["role_id"]] += 1

    first_elim_pct = {
        role: round(cnt / games_per_role.get(role, 1) * 100, 1)
        for role, cnt in first_elim_role.items()
    }

    # Ticks distribution buckets
    ticks_buckets = Counter()
    for t in ticks_list:
        bucket = (t // 10) * 10
        ticks_buckets[bucket] += 1

    # Win rate trend: rolling 100-game windows
    win_rate_trend = {}
    window = 100
    for role in games_per_role:
        trend = []
        for i in range(0, n - window + 1, window // 2):
            chunk = results[i:i + window]
            w = sum(1 for r in chunk if r.get("winner_role") == role)
            cnt = sum(1 for r in chunk for p in r["players"] if p["role_id"] == role)
            trend.append(round(w / max(cnt, 1) * 100, 1))
        win_rate_trend[role] = trend

    # Drain schedule (theoretical)
    drain_schedule = []
    for t in range(TICKS_PER_ACTION, 300, TICKS_PER_ACTION):
        d = DRAIN_BASE * (2 ** ((t - 1) // DRAIN_DOUBLE_EVERY))
        drain_schedule.append({"tick": t, "round": t // TICKS_PER_ACTION, "drain": d})

    return {
        "n_runs": n,
        "no_winner_pct": round(no_winner_count / n * 100, 1),
        "rounds_mean": round(statistics.mean(rounds_list), 1),
        "rounds_median": statistics.median(rounds_list),
        "rounds_min": min(rounds_list),
        "rounds_max": max(rounds_list),
        "rounds_stdev": round(statistics.stdev(rounds_list) if n > 1 else 0, 1),
        "ticks_mean": round(statistics.mean(ticks_list), 1),
        "ticks_median": statistics.median(ticks_list),
        "ticks_min": min(ticks_list),
        "ticks_max": max(ticks_list),
        "ticks_stdev": round(statistics.stdev(ticks_list) if n > 1 else 0, 1),
        "winner_time_mean": round(statistics.mean(winner_times), 1) if winner_times else 0,
        "winner_time_median": statistics.median(winner_times) if winner_times else 0,
        "winner_time_stdev": round(statistics.stdev(winner_times) if len(winner_times) > 1 else 0, 1),
        "wins_per_role": dict(wins_per_role.most_common()),
        "win_rate_per_role": {k: round(v * 100, 1) for k, v in sorted(win_rate_per_role.items(), key=lambda x: -x[1])},
        "role_avg_place": dict(sorted(role_avg_place.items(), key=lambda x: x[1])),
        "role_action_pct": dict(role_action_pct),
        "first_eliminated_pct": dict(sorted(first_elim_pct.items(), key=lambda x: -x[1])),
        "role_avg_elim_round": dict(sorted(role_avg_elim_round.items(), key=lambda x: x[1])),
        "role_avg_elim_tick": dict(sorted(role_avg_elim_tick.items(), key=lambda x: x[1])),
        "ticks_buckets": dict(sorted(ticks_buckets.items())),
        "win_rate_trend": win_rate_trend,
        "drain_schedule": drain_schedule,
        "params": {
            "base_sec": BASE_SEC,
            "drain_base": DRAIN_BASE,
            "drain_double_every": DRAIN_DOUBLE_EVERY,
            "ticks_per_action": TICKS_PER_ACTION,
            "n_agents": len(AGENTS),
        },
    }


def _role_color(role: str, alpha: float = 1.0) -> str:
    colors = {
        "role_snake":       f"rgba(239,68,68,{alpha})",
        "role_peacekeeper": f"rgba(34,197,94,{alpha})",
        "role_banker":      f"rgba(250,204,21,{alpha})",
        "role_gambler":     f"rgba(168,85,247,{alpha})",
    }
    return colors.get(role, f"rgba(148,163,184,{alpha})")


def generate_html_report(stats: dict, out_path: Path, run_time_sec: float) -> None:
    roles = list(stats["win_rate_per_role"].keys())
    role_labels_js = json.dumps([ROLE_LABELS.get(r, r) for r in roles])
    expected_pct = 100 / stats["params"]["n_agents"]

    # Win rate bar data
    win_rates = [stats["win_rate_per_role"][r] for r in roles]
    win_colors = [_role_color(r) for r in roles]

    # Avg place data
    avg_place_roles = list(stats["role_avg_place"].keys())
    avg_place_vals = [stats["role_avg_place"][r] for r in avg_place_roles]
    avg_place_labels = json.dumps([ROLE_LABELS.get(r, r) for r in avg_place_roles])
    avg_place_colors = [_role_color(r) for r in avg_place_roles]

    # First eliminated
    first_elim_roles = list(stats["first_eliminated_pct"].keys())
    first_elim_vals = [stats["first_eliminated_pct"][r] for r in first_elim_roles]
    first_elim_labels = json.dumps([ROLE_LABELS.get(r, r) for r in first_elim_roles])
    first_elim_colors = [_role_color(r) for r in first_elim_roles]

    # Ticks histogram
    ticks_buckets = stats["ticks_buckets"]
    tick_labels = json.dumps([str(k) for k in sorted(ticks_buckets.keys())])
    tick_vals = json.dumps([ticks_buckets[k] for k in sorted(ticks_buckets.keys())])

    # Drain schedule
    drain_sched = stats["drain_schedule"]
    drain_rounds = json.dumps([d["round"] for d in drain_sched])
    drain_vals = json.dumps([d["drain"] for d in drain_sched])

    # Action distribution per role (stacked bar)
    action_types = ["steal", "cooperate", "use_code", "pass"]
    action_labels = json.dumps(["Крадіжка", "Кооперація", "Код", "Пас"])
    action_colors = ["rgba(239,68,68,0.85)", "rgba(34,197,94,0.85)", "rgba(250,204,21,0.85)", "rgba(148,163,184,0.6)"]
    action_datasets = []
    for i, act in enumerate(action_types):
        vals = [stats["role_action_pct"].get(r, {}).get(act, 0) for r in roles]
        action_datasets.append({
            "label": ["Крадіжка", "Кооперація", "Код", "Пас"][i],
            "data": vals,
            "backgroundColor": action_colors[i],
        })

    # Win rate trend
    trend_datasets = []
    trend_labels_count = max((len(v) for v in stats["win_rate_trend"].values()), default=0)
    trend_x_labels = json.dumps([f"~{(i * 50) + 50}" for i in range(trend_labels_count)])
    for role, trend in stats["win_rate_trend"].items():
        trend_datasets.append({
            "label": ROLE_LABELS.get(role, role),
            "data": trend,
            "borderColor": _role_color(role),
            "backgroundColor": _role_color(role, 0.1),
            "tension": 0.3,
            "fill": False,
        })

    # Avg elimination round per role
    elim_round_roles = list(stats["role_avg_elim_round"].keys())
    elim_round_vals = [stats["role_avg_elim_round"][r] for r in elim_round_roles]
    elim_round_labels = json.dumps([ROLE_LABELS.get(r, r) for r in elim_round_roles])
    elim_round_colors = [_role_color(r) for r in elim_round_roles]

    # Avg elimination tick per role (separate from round)
    elim_tick_roles = list(stats["role_avg_elim_tick"].keys())
    elim_tick_vals = [stats["role_avg_elim_tick"][r] for r in elim_tick_roles]
    elim_tick_labels = json.dumps([ROLE_LABELS.get(r, r) for r in elim_tick_roles])
    elim_tick_colors = [_role_color(r) for r in elim_tick_roles]

    # Pre-build table rows (avoid nested f-string/dict issues)
    table_rows_html = ""
    for r in roles:
        act = stats["role_action_pct"].get(r) or {}
        wr = stats["win_rate_per_role"].get(r, 0)
        bar_w = int(wr / 30 * 100)
        rc = _role_color(r)
        rc_dim = _role_color(r, 0.2)
        label = ROLE_LABELS.get(r, r)
        avg_pl = stats["role_avg_place"].get(r, "-")
        first_el = stats["first_eliminated_pct"].get(r, "-")
        avg_et = stats["role_avg_elim_tick"].get(r, "-")
        avg_er = stats["role_avg_elim_round"].get(r, "-")
        coop = act.get("cooperate", "-")
        steal = act.get("steal", "-")
        code_ = act.get("use_code", "-")
        pass_ = act.get("pass", "-")
        table_rows_html += (
            f'<tr>'
            f'<td><span class="role-badge" style="background:{rc_dim};color:{rc}">{label}</span></td>'
            f'<td><b>{wr}%</b><div class="bar"><div class="bar-fill" style="width:{bar_w}%;background:{rc}"></div></div></td>'
            f'<td>{avg_pl}</td>'
            f'<td>{first_el}%</td>'
            f'<td>{avg_et}</td>'
            f'<td>{avg_er}</td>'
            f'<td>{coop}%</td>'
            f'<td>{steal}%</td>'
            f'<td>{code_}%</td>'
            f'<td>{pass_}%</td>'
            f'</tr>\n'
        )

    html = f"""<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TIME WARS — Аналіз {stats['n_runs']} симуляцій</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0a0f1a; color: #e2e8f0; font-family: 'Segoe UI', system-ui, sans-serif; padding: 24px; }}
  h1 {{ font-size: 1.8rem; color: #38bdf8; margin-bottom: 6px; }}
  .subtitle {{ color: #64748b; font-size: .9rem; margin-bottom: 28px; }}
  .grid {{ display: grid; gap: 20px; }}
  .grid-2 {{ grid-template-columns: 1fr 1fr; }}
  .grid-3 {{ grid-template-columns: 1fr 1fr 1fr; }}
  .grid-4 {{ grid-template-columns: repeat(4, 1fr); }}
  .card {{ background: #0f1f35; border: 1px solid #1e3a5f; border-radius: 12px; padding: 20px; }}
  .card h2 {{ font-size: .95rem; color: #94a3b8; text-transform: uppercase; letter-spacing: .06em; margin-bottom: 16px; }}
  .stat-card {{ text-align: center; }}
  .stat-val {{ font-size: 2.4rem; font-weight: 700; color: #38bdf8; line-height: 1; }}
  .stat-val.good {{ color: #22c55e; }}
  .stat-val.warn {{ color: #f59e0b; }}
  .stat-label {{ font-size: .8rem; color: #64748b; margin-top: 6px; }}
  .stat-sub {{ font-size: .75rem; color: #475569; margin-top: 4px; }}
  canvas {{ max-height: 280px; }}
  .role-badge {{ display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 6px; font-size: .82rem; font-weight: 600; margin: 2px; }}
  .sep {{ border: none; border-top: 1px solid #1e3a5f; margin: 24px 0; }}
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .85rem; }}
  th {{ color: #64748b; text-align: left; padding: 8px 12px; border-bottom: 1px solid #1e3a5f; font-weight: 600; text-transform: uppercase; font-size: .75rem; letter-spacing: .05em; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #0f2444; }}
  tr:last-child td {{ border-bottom: none; }}
  .bar {{ height: 8px; border-radius: 4px; background: #1e3a5f; overflow: hidden; margin-top: 4px; }}
  .bar-fill {{ height: 100%; border-radius: 4px; }}
  @media (max-width: 900px) {{ .grid-2, .grid-3, .grid-4 {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<h1>⚔ TIME WARS — Аналіз симуляцій</h1>
<p class="subtitle">{stats['n_runs']} ігор · base_sec={stats['params']['base_sec']} · drain_base={stats['params']['drain_base']} · drain_double_every={stats['params']['drain_double_every']} тіків · Час виконання: {run_time_sec:.1f}с</p>

<!-- Top stat cards -->
<div class="grid grid-4" style="margin-bottom:20px">
  <div class="card stat-card">
    <div class="stat-val">{stats['n_runs']}</div>
    <div class="stat-label">Ігор зіграно</div>
  </div>
  <div class="card stat-card">
    <div class="stat-val {'good' if stats['no_winner_pct'] == 0 else 'warn'}">{stats['no_winner_pct']}%</div>
    <div class="stat-label">Нічиїх</div>
    <div class="stat-sub">{'Ідеально ✓' if stats['no_winner_pct'] == 0 else 'Tie-break needed'}</div>
  </div>
  <div class="card stat-card">
    <div class="stat-val">{stats['rounds_mean']}</div>
    <div class="stat-label">Раундів (середнє)</div>
    <div class="stat-sub">σ={stats['rounds_stdev']} · {stats['rounds_min']}–{stats['rounds_max']}</div>
  </div>
  <div class="card stat-card">
    <div class="stat-val">{stats['ticks_mean']}</div>
    <div class="stat-label">Тіків (середнє)</div>
    <div class="stat-sub">σ={stats['ticks_stdev']} · {stats['ticks_min']}–{stats['ticks_max']}</div>
  </div>
</div>

<div class="grid grid-4" style="margin-bottom:24px">
  <div class="card stat-card">
    <div class="stat-val warn">{stats['winner_time_mean']:.0f}с</div>
    <div class="stat-label">Час переможця (середнє)</div>
    <div class="stat-sub">σ={stats['winner_time_stdev']:.0f}с</div>
  </div>
  <div class="card stat-card">
    <div class="stat-val">{stats['winner_time_median']:.0f}с</div>
    <div class="stat-label">Час переможця (медіана)</div>
  </div>
  <div class="card stat-card">
    <div class="stat-val">{run_time_sec/stats['n_runs']*1000:.1f}мс</div>
    <div class="stat-label">Швидкість / гра</div>
  </div>
  <div class="card stat-card">
    <div class="stat-val">{round(run_time_sec/stats['n_runs']*1000/stats['ticks_mean'],3):.3f}мс</div>
    <div class="stat-label">Швидкість / тік</div>
  </div>
</div>

<!-- Row 1: Win rate + Avg place -->
<div class="grid grid-2" style="margin-bottom:20px">
  <div class="card">
    <h2>% Перемог по ролях (очікується {expected_pct:.1f}%)</h2>
    <canvas id="winRateChart"></canvas>
  </div>
  <div class="card">
    <h2>Середнє місце по ролях (1 = найкраще)</h2>
    <canvas id="avgPlaceChart"></canvas>
  </div>
</div>

<!-- Row 2: Action dist + First eliminated -->
<div class="grid grid-2" style="margin-bottom:20px">
  <div class="card">
    <h2>Розподіл дій по ролях (%)</h2>
    <canvas id="actionChart"></canvas>
  </div>
  <div class="card">
    <h2>Хто вилітає першим (%)</h2>
    <canvas id="firstElimChart"></canvas>
  </div>
</div>

<!-- Row 3: Ticks histogram + Drain schedule -->
<div class="grid grid-2" style="margin-bottom:20px">
  <div class="card">
    <h2>Розподіл кількості тіків на гру</h2>
    <canvas id="ticksHistChart"></canvas>
  </div>
  <div class="card">
    <h2>Ескалація дрейну (тіків/тік)</h2>
    <canvas id="drainChart"></canvas>
  </div>
</div>

<!-- Row 4: Win rate trend + Avg elim tick -->
<div class="grid grid-2" style="margin-bottom:20px">
  <div class="card">
    <h2>Тренд % перемог (вікна по 100 ігор)</h2>
    <canvas id="trendChart"></canvas>
  </div>
  <div class="card">
    <h2>Середній тік вилучення по ролях</h2>
    <canvas id="elimTickChart"></canvas>
  </div>
</div>

<!-- Detailed table -->
<div class="card" style="margin-bottom:20px">
  <h2>Детальна таблиця по ролях</h2>
  <div class="table-wrap">
  <table>
    <tr>
      <th>Роль</th>
      <th>% перемог</th>
      <th>Avg місце</th>
      <th>Перших виліт</th>
      <th>Avg тік виліт</th>
      <th>Avg раунд виліт</th>
      <th>coop%</th>
      <th>steal%</th>
      <th>code%</th>
      <th>pass%</th>
    </tr>
    {table_rows_html}
  </table>
  </div>
</div>

<script>
const EXPECTED = {expected_pct:.2f};
const roleLabels = {role_labels_js};
const roleColors = {json.dumps(win_colors)};

// Win Rate Chart
new Chart(document.getElementById('winRateChart'), {{
  type: 'bar',
  data: {{
    labels: roleLabels,
    datasets: [
      {{ label: '% Перемог', data: {json.dumps(win_rates)}, backgroundColor: roleColors, borderRadius: 6 }},
      {{ label: 'Очікується', data: {json.dumps([round(expected_pct,1)]*len(roles))},
         type: 'line', borderColor: 'rgba(148,163,184,0.6)', borderDash: [6,4],
         pointRadius: 0, borderWidth: 2, fill: false }}
    ]
  }},
  options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }},
    scales: {{ y: {{ beginAtZero: true, max: 35, grid: {{ color: '#1e3a5f' }}, ticks: {{ color: '#94a3b8', callback: v => v+'%' }} }},
               x: {{ grid: {{ display: false }}, ticks: {{ color: '#e2e8f0' }} }} }} }}
}});

// Avg Place Chart
new Chart(document.getElementById('avgPlaceChart'), {{
  type: 'bar',
  data: {{
    labels: {avg_place_labels},
    datasets: [{{ label: 'Середнє місце', data: {json.dumps(avg_place_vals)},
      backgroundColor: {json.dumps(avg_place_colors)}, borderRadius: 6 }}]
  }},
  options: {{ indexAxis: 'y', responsive: true, plugins: {{ legend: {{ display: false }} }},
    scales: {{ x: {{ min: 1, max: 6, grid: {{ color: '#1e3a5f' }}, ticks: {{ color: '#94a3b8' }} }},
               y: {{ grid: {{ display: false }}, ticks: {{ color: '#e2e8f0' }} }} }} }}
}});

// Action Distribution Stacked Bar
new Chart(document.getElementById('actionChart'), {{
  type: 'bar',
  data: {{
    labels: roleLabels,
    datasets: {json.dumps(action_datasets)}
  }},
  options: {{ responsive: true, plugins: {{ legend: {{ position: 'bottom', labels: {{ color: '#94a3b8', boxWidth: 12 }} }} }},
    scales: {{ x: {{ stacked: true, grid: {{ display: false }}, ticks: {{ color: '#e2e8f0' }} }},
               y: {{ stacked: true, max: 100, grid: {{ color: '#1e3a5f' }}, ticks: {{ color: '#94a3b8', callback: v => v+'%' }} }} }} }}
}});

// First Eliminated Chart
new Chart(document.getElementById('firstElimChart'), {{
  type: 'doughnut',
  data: {{
    labels: {first_elim_labels},
    datasets: [{{ data: {json.dumps(first_elim_vals)}, backgroundColor: {json.dumps(first_elim_colors)}, borderWidth: 2, borderColor: '#0a0f1a' }}]
  }},
  options: {{ responsive: true, plugins: {{
    legend: {{ position: 'bottom', labels: {{ color: '#94a3b8', boxWidth: 12 }} }},
    tooltip: {{ callbacks: {{ label: ctx => ctx.label + ': ' + ctx.parsed + '%' }} }}
  }} }}
}});

// Ticks Histogram
new Chart(document.getElementById('ticksHistChart'), {{
  type: 'bar',
  data: {{
    labels: {tick_labels},
    datasets: [{{ label: 'Кількість ігор', data: {tick_vals},
      backgroundColor: 'rgba(56,189,248,0.7)', borderRadius: 4 }}]
  }},
  options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ grid: {{ display: false }}, ticks: {{ color: '#94a3b8' }}, title: {{ display: true, text: 'Тіків', color: '#64748b' }} }},
      y: {{ grid: {{ color: '#1e3a5f' }}, ticks: {{ color: '#94a3b8' }}, title: {{ display: true, text: 'Ігор', color: '#64748b' }} }}
    }}
  }}
}});

// Drain Schedule
new Chart(document.getElementById('drainChart'), {{
  type: 'line',
  data: {{
    labels: {drain_rounds},
    datasets: [{{ label: 'Дрейн (с/тік)', data: {drain_vals},
      borderColor: 'rgba(239,68,68,0.9)', backgroundColor: 'rgba(239,68,68,0.1)',
      fill: true, tension: 0.1, pointRadius: 3, pointBackgroundColor: 'rgba(239,68,68,0.9)' }}]
  }},
  options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ grid: {{ display: false }}, ticks: {{ color: '#94a3b8' }}, title: {{ display: true, text: 'Раунд', color: '#64748b' }} }},
      y: {{ grid: {{ color: '#1e3a5f' }}, ticks: {{ color: '#94a3b8' }}, title: {{ display: true, text: 'с/тік', color: '#64748b' }} }}
    }}
  }}
}});

// Win Rate Trend
new Chart(document.getElementById('trendChart'), {{
  type: 'line',
  data: {{
    labels: {trend_x_labels},
    datasets: {json.dumps(trend_datasets)}
  }},
  options: {{ responsive: true,
    plugins: {{
      legend: {{ position: 'bottom', labels: {{ color: '#94a3b8', boxWidth: 12 }} }},
      tooltip: {{ mode: 'index' }}
    }},
    scales: {{
      x: {{ grid: {{ color: '#1e3a5f' }}, ticks: {{ color: '#94a3b8' }}, title: {{ display: true, text: 'Гра #', color: '#64748b' }} }},
      y: {{ grid: {{ color: '#1e3a5f' }}, ticks: {{ color: '#94a3b8', callback: v => v+'%' }},
           title: {{ display: true, text: '% перемог', color: '#64748b' }},
           suggestedMin: 5, suggestedMax: 30 }}
    }}
  }}
}});

// Avg Elimination Tick
new Chart(document.getElementById('elimTickChart'), {{
  type: 'bar',
  data: {{
    labels: {elim_tick_labels},
    datasets: [{{ label: 'Середній тік вилучення', data: {json.dumps(elim_tick_vals)},
      backgroundColor: {json.dumps(elim_tick_colors)}, borderRadius: 6 }}]
  }},
  options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ grid: {{ display: false }}, ticks: {{ color: '#e2e8f0' }} }},
      y: {{ grid: {{ color: '#1e3a5f' }}, ticks: {{ color: '#94a3b8' }},
           title: {{ display: true, text: 'Тік', color: '#64748b' }} }}
    }}
  }}
}});
</script>
</body>
</html>"""

    out_path.write_text(html, encoding="utf-8")
    print(f"HTML report: {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--out", type=Path, default=ROOT / "sim_results.json")
    parser.add_argument("--html", type=Path, default=ROOT / "sim_report.html")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    codes_catalog = load_codes()

    t0 = time.perf_counter()
    results = []
    print(f"Starting {args.runs} games...", flush=True)
    for i in range(1, args.runs + 1):
        res = run_one_game(i, rng, codes_catalog)
        results.append(res)
        if i % 100 == 0:
            elapsed = time.perf_counter() - t0
            print(f"  {i}/{args.runs} ({elapsed:.1f}s)", flush=True)

    elapsed = time.perf_counter() - t0
    print(f"Done! {args.runs} games in {elapsed:.1f}s ({elapsed/args.runs*1000:.1f}ms/game)")

    stats = aggregate(results)

    # Print key stats
    print(f"\nTicks: mean={stats['ticks_mean']} median={stats['ticks_median']} stdev={stats['ticks_stdev']} ({stats['ticks_min']}-{stats['ticks_max']})")
    print(f"Rounds: mean={stats['rounds_mean']} median={stats['rounds_median']} stdev={stats['rounds_stdev']} ({stats['rounds_min']}-{stats['rounds_max']})")
    print(f"No winner: {stats['no_winner_pct']}%")
    print(f"Winner time: mean={stats['winner_time_mean']:.0f}s median={stats['winner_time_median']:.0f}s\n")
    print("Win rate:")
    for role, pct in stats["win_rate_per_role"].items():
        label = ROLE_LABELS.get(role, role)
        bar = "#" * int(pct / 2)
        print(f"  {label:20s} {pct:5.1f}%  {bar}")
    print("\nAvg elimination tick:")
    for role, tick_val in stats["role_avg_elim_tick"].items():
        label = ROLE_LABELS.get(role, role)
        print(f"  {label:20s} tick {tick_val}")

    args.out.write_text(json.dumps({"stats": stats, "results": results}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nJSON saved: {args.out}")

    generate_html_report(stats, args.html, elapsed)

    if not args.no_browser:
        webbrowser.open(args.html.as_uri())

    return 0


if __name__ == "__main__":
    sys.exit(main())
