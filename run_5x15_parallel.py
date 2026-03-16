"""
run_5x15_parallel.py

Запускає 5 ігор по 15 раундів кожна.
За замовчуванням — паралельно (5 процесів); з --sequential — по черзі (одні й ті самі
агенти, пам'ять і стан накопичуються між іграми).
Використовує .env (OPENROUTER_API_KEY) або --keys-file як у run_one_game.
Рекомендовано передавати --keys-file при паралельному запуску кількох ігор.

Usage:
  python run_5x15_parallel.py --html
  python run_5x15_parallel.py --keys-file openrouter_keys.txt --html
  python run_5x15_parallel.py --sequential --html   # 5 ігор по черзі (еволюція агентів)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOTAL_GAMES = 5
ROUNDS = 15


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return env


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
        description=f"Run {TOTAL_GAMES} games in parallel, {ROUNDS} rounds each.",
    )
    parser.add_argument(
        "--keys-file",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to file with one OpenRouter key per line (optional; else uses .env OPENROUTER_API_KEY).",
    )
    parser.add_argument(
        "--sequential",
        action="store_true",
        help="Run 5 games one after another (same agents; memory and state persist between games).",
    )
    args, pass_through = parser.parse_known_args()

    pass_through_str = list(pass_through)
    if "--rounds" not in pass_through_str:
        pass_through_str.extend(["--rounds", str(ROUNDS)])
    if "--html" not in pass_through_str:
        pass_through_str.append("--html")

    if args.keys_file is not None and args.keys_file.exists():
        keys = load_keys_from_file(args.keys_file)
        if not keys:
            print("run_5x15_parallel: no keys in file.", file=sys.stderr)
            return 1
        run_one_game_script = str(ROOT / "run_one_game.py")
        base_argv = [
            sys.executable,
            run_one_game_script,
            "--keys-file",
            str(args.keys_file.resolve()),
        ] + pass_through_str
        use_run_one_game = True
    else:
        print(
            "run_5x15_parallel: --keys-file not set; using single OPENROUTER_API_KEY. "
            "For 5 parallel games, --keys-file is recommended to reduce rate limit risk.",
            file=sys.stderr,
        )
        run_simulation_script = str(ROOT / "run_simulation_live.py")
        base_argv = [sys.executable, run_simulation_script] + pass_through_str
        use_run_one_game = False

    if args.sequential:
        # Run 5 games one after another; same agents, memory/state persist
        run_simulation_script = str(ROOT / "run_simulation_live.py")
        exit_codes = []
        for game_id in range(1, TOTAL_GAMES + 1):
            argv = [sys.executable, run_simulation_script, "--name", f"game_{game_id}"] + pass_through_str
            log_path = ROOT / "logs" / f"run_5x15_game_{game_id}.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "w", encoding="utf-8") as logf:
                code = subprocess.run(argv, cwd=ROOT, stdout=logf, stderr=subprocess.STDOUT, env=_child_env()).returncode
            exit_codes.append((game_id, code, log_path))
            if code != 0 and log_path.exists():
                tail = log_path.read_text(encoding="utf-8", errors="replace").strip()[-1500:]
                if tail:
                    print(f"--- game_{game_id} (exit {code}), last lines ---", file=sys.stderr)
                    print(tail, file=sys.stderr)
        ok = sum(1 for (_, c, _) in exit_codes if c == 0)
        print(f"run_5x15_parallel: {ok}/{TOTAL_GAMES} games finished ({ROUNDS} rounds each, sequential).")
        for game_id, code, _ in exit_codes:
            if code != 0:
                print(f"  game_{game_id} exit code {code}", file=sys.stderr)
        return 0 if ok == TOTAL_GAMES else 1

    processes = []
    for game_id in range(1, TOTAL_GAMES + 1):
        if use_run_one_game:
            argv = base_argv + ["--game", str(game_id)]
        else:
            argv = base_argv + ["--name", f"game_{game_id}"]
        log_path = ROOT / "logs" / f"run_5x15_game_{game_id}.log"
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
    print(f"run_5x15_parallel: {ok}/{TOTAL_GAMES} games finished ({ROUNDS} rounds each).")
    for game_id, code, _ in exit_codes:
        if code != 0:
            print(f"  game_{game_id} exit code {code}", file=sys.stderr)
    return 0 if ok == TOTAL_GAMES else 1


if __name__ == "__main__":
    sys.exit(main())
