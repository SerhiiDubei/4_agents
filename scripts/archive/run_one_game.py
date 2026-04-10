"""
run_one_game.py

Запускає одну гру з ключем OpenRouter за номером (1, 2, …).
Ключі циклічно: гра 1→ключ 1, гра 8→ключ 1 (при 7 ключах). З файлу (--keys-file) або env OPENROUTER_KEY_1 …
Решту аргументів передає в run_simulation_live.py.

Usage:
  python run_one_game.py --game 1 --keys-file openrouter_keys.txt --rounds 5 --html
  python run_one_game.py --game 2 --keys-file openrouter_keys.txt --rounds 5 --html
  # 10 ігор паралельно (вручну):
  1..10 | % { Start-Process python -ArgumentList "run_one_game.py","--game",$_,"--keys-file","openrouter_keys.txt","--rounds","5","--html" -NoNewWindow }
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_keys_from_file(path: Path) -> list[str]:
    """One key per line; skip empty and # lines. Line 1 = game 1, etc."""
    text = path.read_text(encoding="utf-8-sig")
    keys = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            keys.append(line)
    return keys


def load_keys_from_env() -> list[str]:
    """OPENROUTER_KEY_1 … OPENROUTER_KEY_10."""
    keys = []
    for i in range(1, 11):
        v = os.environ.get(f"OPENROUTER_KEY_{i}", "").strip()
        if v:
            keys.append(v)
    return keys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one game with OpenRouter key by index (1–10). Pass-through args go to run_simulation_live.py.",
    )
    parser.add_argument(
        "--game",
        type=int,
        default=None,
        metavar="N",
        help="Game index 1, 2, … (key = ((N-1) %% num_keys) + 1)",
    )
    parser.add_argument(
        "--keys-file",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to file with one OpenRouter key per line (line 1 = game 1, etc.). If omitted, use OPENROUTER_KEY_1 … OPENROUTER_KEY_10 from env.",
    )
    args, pass_through = parser.parse_known_args()

    # If --game not set, run run_simulation_live with original argv (minus --keys-file) so --list-agents etc work
    if args.game is None:
        child_argv = [sys.executable, str(ROOT / "run_simulation_live.py")]
        skip_next = False
        for i, a in enumerate(sys.argv[1:], 1):
            if skip_next:
                skip_next = False
                continue
            if a == "--keys-file":
                skip_next = True
                continue
            if a.startswith("--keys-file="):
                continue
            child_argv.append(a)
        return subprocess.run(child_argv, cwd=ROOT, env=os.environ.copy()).returncode

    game_id = args.game
    if game_id < 1:
        print(f"run_one_game: --game must be >= 1, got {game_id}", file=sys.stderr)
        return 1

    if args.keys_file is not None:
        if not args.keys_file.exists():
            print(f"run_one_game: keys file not found: {args.keys_file}", file=sys.stderr)
            return 1
        keys = load_keys_from_file(args.keys_file)
    else:
        keys = load_keys_from_env()

    if not keys:
        print("run_one_game: no keys available (empty file or env).", file=sys.stderr)
        return 1

    key_index = (game_id - 1) % len(keys)
    key = keys[key_index].strip()
    if not key:
        print(f"run_one_game: key for game {game_id} is empty", file=sys.stderr)
        return 1

    os.environ["OPENROUTER_API_KEY"] = key

    child_argv = [
        sys.executable,
        str(ROOT / "run_simulation_live.py"),
        "--name",
        f"game_{game_id}",
    ] + pass_through

    return subprocess.run(child_argv, cwd=ROOT, env=os.environ.copy()).returncode


if __name__ == "__main__":
    sys.exit(main())
