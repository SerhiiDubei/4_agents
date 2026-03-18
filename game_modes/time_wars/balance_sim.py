"""
TIME WARS balance simulator — no agents, math model only.

Runs many games (e.g. 1000) with fixed STATE rules:
- 1 tick = 1 "game minute" (configurable sec per tick)
- Tick: each player loses tick_cost_sec per tick
- Events: storm (all lose X sec), crisis (players below threshold lose Y sec) at scheduled ticks
- Actions: each tick, each player with p_coop / p_steal does one action (coop or steal vs random other)
  Uses same payoffs as constants (COOP_REWARD_EACH, STEAL_*, roll d20)

Output: survival rate, mean/median final time, first elimination tick, etc.
Use to tune B (start time), T (game length), event count/value, p_coop/p_steal.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

# Use same payoffs as real game
from game_modes.time_wars.constants import (
    COOP_REWARD_EACH,
    STEAL_FAIL_ACTOR_PENALTY,
    STEAL_PARTIAL_ACTOR_GAIN,
    STEAL_PARTIAL_TARGET_LOSS,
    STEAL_ROLL_PARTIAL_MIN,
    STEAL_ROLL_SUCCESS_MIN,
    STEAL_SUCCESS_ACTOR_GAIN,
    STEAL_SUCCESS_TARGET_LOSS,
    SECONDS_PER_GAME_MINUTE,
)


@dataclass
class SimEvent:
    tick: int
    kind: str  # "storm" | "crisis"
    # storm
    delta_sec: int = 0
    # crisis
    threshold_sec: int = 0
    penalty_sec: int = 0


@dataclass
class SimParams:
    n_players: int = 4
    B_sec: int = 20 * 60  # start time per player (20 min default)
    T_ticks: int = 20
    tick_cost_sec: int = SECONDS_PER_GAME_MINUTE  # 1 tick = 1 game minute
    events: List[SimEvent] = field(default_factory=list)
    p_coop: float = 0.3
    p_steal: float = 0.2
    p_code_use: float = 0.0  # optional: use one code per run
    action_every_n_ticks: int = 1  # run action phase every N ticks
    seed: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "n_players": self.n_players,
            "B_sec": self.B_sec,
            "T_ticks": self.T_ticks,
            "tick_cost_sec": self.tick_cost_sec,
            "events": [
                {
                    "tick": e.tick,
                    "kind": e.kind,
                    "delta_sec": e.delta_sec,
                    "threshold_sec": e.threshold_sec,
                    "penalty_sec": e.penalty_sec,
                }
                for e in self.events
            ],
            "p_coop": self.p_coop,
            "p_steal": self.p_steal,
            "p_code_use": self.p_code_use,
            "action_every_n_ticks": self.action_every_n_ticks,
        }


def run_one(params: SimParams, rng: random.Random) -> dict:
    """
    Run a single game. Returns dict with:
    - final_times: list of time_remaining_sec per player at end (0 if eliminated)
    - eliminated_at: list of tick when eliminated (T_ticks+1 if survived)
    - n_survivors: count of players with time > 0 at end
    - first_elimination_tick: tick of first elimination or T_ticks+1
    """
    n = params.n_players
    time_sec = [params.B_sec] * n
    eliminated_at = [params.T_ticks + 1] * n  # survived

    for t in range(1, params.T_ticks + 1):
        # 1) Tick: everyone loses tick_cost_sec
        for i in range(n):
            if time_sec[i] <= 0:
                continue
            time_sec[i] = max(0, time_sec[i] - params.tick_cost_sec)
            if time_sec[i] <= 0:
                eliminated_at[i] = t

        # 2) Scheduled events
        for ev in params.events:
            if ev.tick != t:
                continue
            if ev.kind == "storm":
                for i in range(n):
                    if time_sec[i] > 0:
                        time_sec[i] = max(0, time_sec[i] + ev.delta_sec)
                        if time_sec[i] <= 0:
                            eliminated_at[i] = t
            elif ev.kind == "crisis":
                for i in range(n):
                    if time_sec[i] > 0 and time_sec[i] < ev.threshold_sec:
                        time_sec[i] = max(0, time_sec[i] + ev.penalty_sec)
                        if time_sec[i] <= 0:
                            eliminated_at[i] = t

        # 3) Actions (only active players, every action_every_n_ticks)
        if t % params.action_every_n_ticks != 0:
            continue
        active = [i for i in range(n) if time_sec[i] > 0]
        if len(active) < 2:
            continue

        # Decide action per player (simplified: one action per tick, coop or steal)
        actions: List[Optional[tuple]] = [None] * n  # (action_type, target_index) or None
        for i in active:
            r = rng.random()
            if r < params.p_coop:
                other = rng.choice([j for j in active if j != i])
                actions[i] = ("coop", other)
            elif r < params.p_coop + params.p_steal:
                other = rng.choice([j for j in active if j != i])
                actions[i] = ("steal", other)

        # Resolve coop (each unordered pair once: both +COOP_REWARD_EACH)
        seen_pairs: set = set()
        for i in active:
            if actions[i] is None or actions[i][0] != "coop":
                continue
            _, j = actions[i]
            if j is None or time_sec[j] <= 0:
                continue
            pair = (min(i, j), max(i, j))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            time_sec[i] += COOP_REWARD_EACH
            time_sec[j] += COOP_REWARD_EACH

        # Resolve steal (d20 + payoffs)
        for i in active:
            if actions[i] is None or actions[i][0] != "steal":
                continue
            _, j = actions[i]
            if j is None or time_sec[j] <= 0:
                continue
            roll = rng.randint(1, 20)
            if roll >= STEAL_ROLL_SUCCESS_MIN:
                actor_gain = STEAL_SUCCESS_ACTOR_GAIN
                target_loss = min(time_sec[j], STEAL_SUCCESS_TARGET_LOSS)
            elif roll >= STEAL_ROLL_PARTIAL_MIN:
                actor_gain = STEAL_PARTIAL_ACTOR_GAIN
                target_loss = min(time_sec[j], STEAL_PARTIAL_TARGET_LOSS)
            else:
                actor_gain = -STEAL_FAIL_ACTOR_PENALTY
                target_loss = 0
            time_sec[i] = max(0, time_sec[i] + actor_gain)
            time_sec[j] = max(0, time_sec[j] - target_loss)
            if time_sec[j] <= 0:
                eliminated_at[j] = t

    n_survivors = sum(1 for x in time_sec if x > 0)
    first_elim = min(eliminated_at) if any(x <= params.T_ticks for x in eliminated_at) else params.T_ticks + 1

    return {
        "final_times": list(time_sec),
        "eliminated_at": list(eliminated_at),
        "n_survivors": n_survivors,
        "first_elimination_tick": first_elim,
    }


def run_many(params: SimParams, n_runs: int, seed: Optional[int] = None) -> dict:
    """Run n_runs games, aggregate metrics."""
    rng = random.Random(seed)
    all_final_times: List[List[int]] = []
    all_n_survivors: List[int] = []
    all_first_elim: List[int] = []

    for _ in range(n_runs):
        res = run_one(params, rng)
        all_final_times.append(res["final_times"])
        all_n_survivors.append(res["n_survivors"])
        all_first_elim.append(res["first_elimination_tick"])

    # Flatten final times (per player, per run)
    flat_times = [t for run in all_final_times for t in run]
    survivors_per_run = all_n_survivors

    return {
        "params": params.to_dict(),
        "n_runs": n_runs,
        "final_time_mean": statistics.mean(flat_times),
        "final_time_median": statistics.median(flat_times),
        "final_time_stdev": statistics.stdev(flat_times) if len(flat_times) > 1 else 0,
        "survival_rate": sum(1 for s in survivors_per_run if s >= 1) / n_runs,
        "survival_rate_2plus": sum(1 for s in survivors_per_run if s >= 2) / n_runs,
        "mean_survivors_per_run": statistics.mean(survivors_per_run),
        "first_elimination_tick_mean": statistics.mean(all_first_elim),
        "first_elimination_tick_median": statistics.median(all_first_elim),
    }


def default_param_sets() -> List[SimParams]:
    """Default grid for balance tuning: B, T, events, p_coop/p_steal."""
    B_20 = 20 * 60
    B_25 = 25 * 60
    B_30 = 30 * 60
    sets: List[SimParams] = []

    for B_sec in (B_20, B_25, B_30):
        for T in (15, 20, 25):
            if T > 0:
                # No events
                sets.append(SimParams(B_sec=B_sec, T_ticks=T, events=[], p_coop=0.3, p_steal=0.2))
                # 1 storm at half
                sets.append(SimParams(
                    B_sec=B_sec,
                    T_ticks=T,
                    events=[SimEvent(tick=max(1, T // 2), kind="storm", delta_sec=-4 * 60)],
                    p_coop=0.3,
                    p_steal=0.2,
                ))
                # storm + crisis
                sets.append(SimParams(
                    B_sec=B_sec,
                    T_ticks=T,
                    events=[
                        SimEvent(tick=max(1, T // 2), kind="storm", delta_sec=-4 * 60),
                        SimEvent(tick=int(T * 0.7), kind="crisis", threshold_sec=5 * 60, penalty_sec=-3 * 60),
                    ],
                    p_coop=0.3,
                    p_steal=0.2,
                ))

    # Vary behaviour
    for p_coop, p_steal in ((0.5, 0.1), (0.2, 0.4)):
        sets.append(SimParams(
            B_sec=B_20,
            T_ticks=20,
            events=[
                SimEvent(tick=10, kind="storm", delta_sec=-4 * 60),
                SimEvent(tick=14, kind="crisis", threshold_sec=5 * 60, penalty_sec=-3 * 60),
            ],
            p_coop=p_coop,
            p_steal=p_steal,
        ))
    return sets


def main() -> int:
    parser = argparse.ArgumentParser(description="TIME WARS balance simulator (no agents)")
    parser.add_argument("--runs", type=int, default=1000, help="Runs per param set")
    parser.add_argument("--grid", action="store_true", help="Run default param grid")
    parser.add_argument("--B", type=int, default=20, help="Start time per player (game minutes)")
    parser.add_argument("--T", type=int, default=20, help="Game length (ticks = game minutes)")
    parser.add_argument("--storm-tick", type=int, default=None, help="Tick for storm (default T/2)")
    parser.add_argument("--storm-sec", type=int, default=-240, help="Storm delta seconds (-240 = -4 min)")
    parser.add_argument("--crisis-tick", type=int, default=None, help="Tick for crisis (default 0.7*T)")
    parser.add_argument("--crisis-threshold-sec", type=int, default=300, help="Crisis threshold (sec)")
    parser.add_argument("--crisis-penalty-sec", type=int, default=-180, help="Crisis penalty (sec)")
    parser.add_argument("--p-coop", type=float, default=0.3)
    parser.add_argument("--p-steal", type=float, default=0.2)
    parser.add_argument("--players", type=int, default=4)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--out", type=Path, default=None, help="Write JSON summary here")
    args = parser.parse_args()

    if args.grid:
        results = []
        for i, p in enumerate(default_param_sets()):
            m = run_many(p, n_runs=args.runs, seed=args.seed)
            results.append(m)
            print(f"--- Param set {i + 1} ---")
            print(f"  B={p.B_sec // 60}min T={p.T_ticks} events={len(p.events)} p_coop={p.p_coop} p_steal={p.p_steal}")
            print(f"  survival_rate={m['survival_rate']:.2%} mean_final_time={m['final_time_mean']:.0f}s first_elim_median={m['first_elimination_tick_median']:.0f}")
        if args.out:
            args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")
            print(f"Wrote {args.out}")
        return 0

    # Single param set
    T = args.T
    events: List[SimEvent] = []
    if args.storm_tick is not None or args.storm_sec != 0:
        tick = args.storm_tick if args.storm_tick is not None else max(1, T // 2)
        events.append(SimEvent(tick=tick, kind="storm", delta_sec=args.storm_sec))
    if args.crisis_tick is not None or args.crisis_penalty_sec != 0:
        tick = args.crisis_tick if args.crisis_tick is not None else int(T * 0.7)
        events.append(SimEvent(tick=tick, kind="crisis", threshold_sec=args.crisis_threshold_sec, penalty_sec=args.crisis_penalty_sec))

    params = SimParams(
        n_players=args.players,
        B_sec=args.B * 60,
        T_ticks=T,
        events=events,
        p_coop=args.p_coop,
        p_steal=args.p_steal,
        seed=args.seed,
    )
    out = run_many(params, n_runs=args.runs, seed=args.seed)
    print(json.dumps(out, indent=2))
    if args.out:
        args.out.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
