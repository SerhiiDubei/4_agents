"""
run_3x7_parallel.py

Запускає одночасно 3 ігри (по 7 раундів кожна, якщо передати --rounds 7).
Приймає ті самі аргументи, що й run_one_game (--keys-file, --rounds, --html тощо), крім --game.

Usage:
  python run_3x7_parallel.py --keys-file openrouter_keys.txt --rounds 7 --html
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

TOTAL_GAMES = 3  # 3 ігри одночасно


def load_keys_from_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig")
    keys = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            keys.append(line)
    return keys


def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"Run {TOTAL_GAMES} games in parallel. Use --rounds 7 for 7 rounds per game.",
    )
    parser.add_argument(
        "--keys-file",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to file with one OpenRouter key per line (required).",
    )
    args, pass_through = parser.parse_known_args()

    if args.keys_file is None or not args.keys_file.exists():
        print("run_3x7_parallel: --keys-file PATH is required and must exist.", file=sys.stderr)
        return 1

    keys = load_keys_from_file(args.keys_file)
    if not keys:
        print("run_3x7_parallel: no keys found in file.", file=sys.stderr)
        return 1

    pass_through_str = list(pass_through)
    run_one_game_script = str(ROOT / "run_one_game.py")

    processes = []
    for game_id in range(1, TOTAL_GAMES + 1):
        argv = [
            sys.executable,
            run_one_game_script,
            "--game",
            str(game_id),
            "--keys-file",
            str(args.keys_file.resolve()),
        ] + pass_through_str
        log_path = ROOT / "logs" / f"run_3x7_game_{game_id}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logf = open(log_path, "w", encoding="utf-8")
        p = subprocess.Popen(
            argv,
            cwd=ROOT,
            stdout=logf,
            stderr=subprocess.STDOUT,
            env=_child_env(),
        )
        processes.append((game_id, p, log_path, logf))

    exit_codes = []
    for game_id, p, log_path, logf in processes:
        code = p.wait()
        logf.close()
        exit_codes.append((game_id, code, log_path))
        if code != 0 and log_path.exists():
            tail = log_path.read_text(encoding="utf-8", errors="replace").strip()[-1500:]
            if tail:
                print(f"--- game_{game_id} (exit {code}), last lines ---", file=sys.stderr)
                print(tail, file=sys.stderr)

    ok = sum(1 for (_, c, _) in exit_codes if c == 0)
    print(f"run_3x7_parallel: {ok}/{TOTAL_GAMES} games finished.")
    for game_id, code, _ in exit_codes:
        if code != 0:
            print(f"  game_{game_id} exit code {code}", file=sys.stderr)
    return 0 if ok == TOTAL_GAMES else 1


if __name__ == "__main__":
    sys.exit(main())
