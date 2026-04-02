"""
run_island_all.py — Запускає Island на порту 8000, гра з УСІМА агентами, HTML результат.

Usage:
    python run_island_all.py              # сервер має вже працювати на :8000
    python run_island_all.py --start      # спочатку запустити сервер, потім гру

Після гри виводить URL HTML-звіту: http://localhost:8000/logs/game_xxx.html
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_all_agent_ids() -> list[str]:
    """Повертає id всіх агентів з roster.json."""
    roster_path = ROOT / "agents" / "roster.json"
    if not roster_path.exists():
        print("ERROR: agents/roster.json не знайдено.")
        sys.exit(1)
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    ids = [a["id"] for a in roster.get("agents", [])]
    return ids


def wait_for_server(url: str = "http://localhost:8000/health", timeout: int = 30) -> bool:
    """Чекає, поки сервер стане доступним."""
    import urllib.request
    for _ in range(timeout):
        try:
            with urllib.request.urlopen(url, timeout=2) as _:
                return True
        except Exception:
            time.sleep(1)
    return False


def run_simulation(agent_ids: list[str], port: int = 8000, total_rounds: int = 5, use_dialog: bool = False) -> dict:
    """Відправляє POST /start-simulation і повертає відповідь."""
    import urllib.request
    import urllib.error

    url = f"http://localhost:{port}/start-simulation"
    body = json.dumps({
        "agent_ids": agent_ids,
        "total_rounds": total_rounds,
        "use_dialog": use_dialog,
        "export_html": True,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description="Island — гра з усіма агентами, HTML результат")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--rounds", type=int, default=5, help="Кількість раундів")
    parser.add_argument("--dialog", action="store_true", help="Увімкнути LLM-діалог (повільніше)")
    parser.add_argument("--start", action="store_true", help="Спочатку запустити сервер (run.py)")
    args = parser.parse_args()

    agent_ids = load_all_agent_ids()
    print(f"Агентів з roster: {len(agent_ids)}")
    print(f"  {agent_ids}\n")

    if args.start:
        print("Запуск Island сервера на порту", args.port, "...")
        proc = subprocess.Popen(
            [sys.executable, str(ROOT / "run.py")],
            cwd=str(ROOT),
            env={**__import__("os").environ, "PORT": str(args.port)},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not wait_for_server(f"http://localhost:{args.port}/health"):
            print("ERROR: Сервер не запустився за 30 с.")
            proc.terminate()
            sys.exit(1)
        print("Сервер готовий.\n")

    print("Запуск симуляції (усі агенти)...")
    try:
        resp = run_simulation(agent_ids, port=args.port, total_rounds=args.rounds, use_dialog=args.dialog)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    winner = resp.get("winner", "")
    report_path = resp.get("report_path")
    base_url = f"http://localhost:{args.port}"
    report_url = f"{base_url}{report_path}" if report_path else None

    print(f"\n{'='*50}")
    print("  РЕЗУЛЬТАТ ГРИ")
    print(f"{'='*50}")
    print(f"  Переможець: {winner}")
    print(f"  Раундів: {resp.get('rounds_played', 0)}")
    if report_url:
        print(f"\n  HTML-звіт: {report_url}")
        print(f"  (відкрий у браузері)")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
