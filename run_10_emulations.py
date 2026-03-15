"""
run_10_emulations.py

Запускає одночасно 10 емуляцій (без LLM), кожна експортує окремий HTML.
Учасники: 8 осіб як останній раз (Павло, Вова, Ліля, Вождь, Марта, Артурчик, Чорна Кішка, Роман Романюк).

Usage:
  python run_10_emulations.py [--rounds N]
  # Результат: logs/emulation_1.html … logs/emulation_10.html
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Run 10 emulations in parallel, each exports one HTML.")
    parser.add_argument("--rounds", type=int, default=10, help="Number of rounds per emulation (default: 10)")
    args = parser.parse_args()

    logs_dir = ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)

    run_emulation = str(ROOT / "run_emulation_html.py")
    processes = []
    for i in range(1, 11):
        out_path = logs_dir / f"emulation_{i}.html"
        argv = [
            sys.executable,
            run_emulation,
            "--rounds", str(args.rounds),
            "--agents", "8",
            "--out", str(out_path),
        ]
        p = subprocess.Popen(argv, cwd=ROOT)
        processes.append((i, p))

    exit_codes = []
    for idx, p in processes:
        code = p.wait()
        exit_codes.append((idx, code))

    ok = sum(1 for _, c in exit_codes if c == 0)
    print(f"run_10_emulations: {ok}/10 emulations finished.")
    for idx, code in exit_codes:
        if code != 0:
            print(f"  emulation_{idx}.html exit code {code}", file=sys.stderr)
    print(f"HTML files: {logs_dir.resolve() / 'emulation_1.html'} … emulation_10.html")
    return 0 if ok == 10 else 1


if __name__ == "__main__":
    sys.exit(main())
