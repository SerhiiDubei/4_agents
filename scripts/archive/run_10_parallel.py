"""
run_10_parallel.py

Запускає N ігор паралельно. За замовчуванням N = кількість ключів у файлі (1 ключ = 1 гра).
Якщо передати --games 21 — запуститься 21 гра одночасно, ключі використовуються циклічно
(наприклад 7 ключів → кожен ключ на 3 гри: 1,8,15 → key1; 2,9,16 → key2; …).

Usage:
  python run_10_parallel.py --keys-file openrouter_keys.txt --rounds 5 --html
  python run_10_parallel.py --keys-file openrouter_keys.txt --games 21 --rounds 7 --html
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def load_keys_from_file(path: Path) -> list[str]:
    """One key per line; skip empty and # lines."""
    text = path.read_text(encoding="utf-8-sig")
    keys = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            keys.append(line)
    return keys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run N games in parallel. By default N = number of keys; use --games to run more (keys used cyclically).",
    )
    parser.add_argument(
        "--keys-file",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to file with one OpenRouter key per line (required for parallel run).",
    )
    parser.add_argument(
        "--games",
        type=int,
        default=None,
        metavar="N",
        help="Total number of games to run in parallel (default: number of keys). Keys are reused cyclically.",
    )
    parser.add_argument(
        "--log-dir",
        action="store_true",
        help="Write each game stdout/stderr to logs/run_parallel_game_<N>.log",
    )
    args, pass_through = parser.parse_known_args()

    if args.keys_file is None or not args.keys_file.exists():
        print("run_10_parallel: --keys-file PATH is required and must exist.", file=sys.stderr)
        return 1

    keys = load_keys_from_file(args.keys_file)
    if not keys:
        print("run_10_parallel: no keys found in file.", file=sys.stderr)
        return 1

    n_games = args.games if args.games is not None else len(keys)
    if n_games < 1:
        print("run_10_parallel: --games must be >= 1.", file=sys.stderr)
        return 1
    pass_through_str = list(pass_through)
    run_one_game_script = str(ROOT / "run_one_game.py")
    log_dir = ROOT / "logs" if args.log_dir else None
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)

    processes = []
    for i in range(1, n_games + 1):
        argv = [
            sys.executable,
            run_one_game_script,
            "--game",
            str(i),
            "--keys-file",
            str(args.keys_file.resolve()),
        ] + pass_through_str
        if log_dir:
            log_path = log_dir / f"run_parallel_game_{i}.log"
            logf = open(log_path, "w", encoding="utf-8")
            p = subprocess.Popen(
                argv,
                cwd=ROOT,
                stdout=logf,
                stderr=subprocess.STDOUT,
                env=_child_env(),
            )
            processes.append((i, p, log_path, logf))
        else:
            p = subprocess.Popen(
                argv,
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=_child_env(),
            )
            processes.append((i, p, None, None))

    exit_codes = []
    for item in processes:
        game_id, p, log_path, logf = item[0], item[1], item[2], item[3]
        code = p.wait()
        if logf is not None:
            logf.close()
        exit_codes.append((game_id, code, log_path))
        if code != 0 and log_path and log_path.exists():
            tail = log_path.read_text(encoding="utf-8", errors="replace").strip()[-1500:]
            if tail:
                print(f"--- game_{game_id} (exit {code}), last lines ---", file=sys.stderr)
                print(tail, file=sys.stderr)

    ok = sum(1 for (_, c, _) in exit_codes if c == 0)
    print(f"run_10_parallel: {ok}/{n_games} games finished successfully.")
    for game_id, code, _ in exit_codes:
        if code != 0:
            print(f"  game_{game_id} exit code {code}", file=sys.stderr)
    return 0 if ok == n_games else 1


if __name__ == "__main__":
    sys.exit(main())
