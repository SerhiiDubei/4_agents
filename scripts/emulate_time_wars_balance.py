"""
Emulate TIME WARS balance: N runs without agents, math model only.
Params: T (ticks), B (start time per player in "game minutes"), n_players,
events (storm/crisis at given ticks), p_coop, p_steal.
Output: survival_rate, mean_final_time, median_final_time, n_eliminated.
Use to tune B, T, event magnitudes.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run_one(
    T: int,
    B: float,
    n_players: int,
    events: list[dict],
    p_coop: float,
    p_steal: float,
    coop_delta: float,
    steal_actor_delta: float,
    steal_target_delta: float,
    rng: random.Random,
) -> tuple[list[float], int]:
    """
    One run. Returns (final_times per player, n_eliminated).
    Time in "game minutes"; each tick -1 per player; coop +coop_delta each; steal +steal_actor_delta/-steal_target_delta.
    """
    time = [B] * n_players
    eliminated = [False] * n_players
    n_eliminated = 0

    for t in range(1, T + 1):
        # Tick: everyone loses 1
        for i in range(n_players):
            if not eliminated[i]:
                time[i] = max(0, time[i] - 1)
                if time[i] <= 0:
                    eliminated[i] = True
                    n_eliminated += 1

        # Scheduled events
        for ev in events:
            if ev.get("tick") != t:
                continue
            typ = ev.get("type", "")
            delta = ev.get("delta", 0)
            if typ == "storm":
                for i in range(n_players):
                    if not eliminated[i]:
                        time[i] = max(0, time[i] + delta)
                        if time[i] <= 0 and not eliminated[i]:
                            eliminated[i] = True
                            n_eliminated += 1
            elif typ == "crisis":
                threshold = ev.get("threshold", 0)
                for i in range(n_players):
                    if not eliminated[i] and time[i] < threshold:
                        time[i] = max(0, time[i] + delta)
                        if time[i] <= 0:
                            eliminated[i] = True
                            n_eliminated += 1

        # Random actions (coop / steal)
        for i in range(n_players):
            if eliminated[i]:
                continue
            if rng.random() < p_coop:
                j = rng.randint(0, n_players - 1)
                if j != i and not eliminated[j]:
                    time[i] += coop_delta
                    time[j] += coop_delta
            if rng.random() < p_steal:
                j = rng.randint(0, n_players - 1)
                if j != i and not eliminated[j]:
                    time[i] += steal_actor_delta
                    time[j] = max(0, time[j] + steal_target_delta)  # steal_target_delta is negative

    return (time, n_eliminated)


def main() -> int:
    parser = argparse.ArgumentParser(description="Emulate TIME WARS balance (no agents)")
    parser.add_argument("--runs", type=int, default=1000, help="Number of runs per config")
    parser.add_argument("--T", type=int, default=20, help="Game length (ticks)")
    parser.add_argument("--B", type=int, default=20, nargs="+", help="Start time per player (one or more)")
    parser.add_argument("--n-players", type=int, default=6)
    parser.add_argument("--p-coop", type=float, default=0.3)
    parser.add_argument("--p-steal", type=float, default=0.2)
    parser.add_argument("--storm-tick", type=int, default=None, help="Tick for storm (default T/2)")
    parser.add_argument("--storm-delta", type=int, default=-4, help="Storm delta (minutes)")
    parser.add_argument("--crisis-tick", type=int, default=None)
    parser.add_argument("--crisis-threshold", type=int, default=5)
    parser.add_argument("--crisis-delta", type=int, default=-3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--csv", action="store_true", help="Output CSV")
    args = parser.parse_args()

    storm_tick = args.storm_tick if args.storm_tick is not None else args.T // 2
    crisis_tick = args.crisis_tick if args.crisis_tick is not None else 3 * args.T // 4
    events = [
        {"tick": storm_tick, "type": "storm", "delta": args.storm_delta},
        {"tick": crisis_tick, "type": "crisis", "threshold": args.crisis_threshold, "delta": args.crisis_delta},
    ]

    coop_delta = 2.0
    steal_actor_delta = 3.0
    steal_target_delta = -2.0

    B_list = args.B if isinstance(args.B, list) else [args.B]
    rng = random.Random(args.seed)

    if args.csv:
        print("B,T,runs,survival_rate,mean_final_time,median_final_time,n_eliminated_mean")

    for B in B_list:
        survival_count = 0
        all_final_times: list[float] = []
        total_eliminated = 0

        for _ in range(args.runs):
            final_times, n_elim = run_one(
                T=args.T,
                B=float(B),
                n_players=args.n_players,
                events=events,
                p_coop=args.p_coop,
                p_steal=args.p_steal,
                coop_delta=coop_delta,
                steal_actor_delta=steal_actor_delta,
                steal_target_delta=steal_target_delta,
                rng=rng,
            )
            if any(t > 0 for t in final_times):
                survival_count += 1
            all_final_times.extend(final_times)
            total_eliminated += n_elim

        survival_rate = survival_count / args.runs
        mean_final = sum(all_final_times) / len(all_final_times) if all_final_times else 0
        sorted_times = sorted(all_final_times)
        mid = len(sorted_times) // 2
        median_final = (sorted_times[mid] + sorted_times[mid - 1]) / 2 if mid > 0 else sorted_times[0] if sorted_times else 0
        n_elim_mean = total_eliminated / args.runs

        if args.csv:
            print(f"{B},{args.T},{args.runs},{survival_rate:.4f},{mean_final:.2f},{median_final:.2f},{n_elim_mean:.2f}")
        else:
            print(f"B={B} T={args.T} runs={args.runs}: survival_rate={survival_rate:.4f} mean_final={mean_final:.2f} median_final={median_final:.2f} n_elim_mean={n_elim_mean:.2f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
