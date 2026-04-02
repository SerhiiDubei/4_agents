"""
deploy.py — Збірка фронтенду + перезапуск серверів (Main API + Time Wars).

IDEA [REFACTOR: ЗБЕРЕГТИ]: Єдиний скрипт для повного deploy. Не розбивати на окремі.

Usage:
  python deploy.py              # збірка + перезапуск обох серверів
  python deploy.py --build     # тільки збірка фронтенду
  python deploy.py --restart   # тільки перезапуск серверів (без збірки)
  python deploy.py --no-build  # перезапуск без збірки (те саме що --restart)

Після deploy:
  Main API  → http://localhost:8000
  Time Wars → http://localhost:5174
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
PORTS = [8000, 5174]


def _free_port(port: int) -> None:
    """Звільнити порт (Windows)."""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
            )
            killed = set()
            for line in result.stdout.splitlines():
                if f":{port} " in line and "LISTENING" in line:
                    parts = line.strip().split()
                    p_id = parts[-1]
                    if p_id not in killed and p_id.isdigit():
                        subprocess.run(
                            ["taskkill", "/F", "/PID", p_id],
                            capture_output=True,
                        )
                        killed.add(p_id)
            if killed:
                print(f"  Порт {port} звільнено (PIDs: {', '.join(killed)})")
        else:
            subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True)
    except Exception as e:
        print(f"  Увага: не вдалося звільнити порт {port}: {e}")


def build_frontend() -> bool:
    """Зібрати фронтенд (npm run build)."""
    print("\n[deploy] Збірка фронтенду...")
    try:
        r = subprocess.run(
            ["npm", "run", "build"],
            cwd=FRONTEND,
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            print(r.stderr or r.stdout)
            return False
        print("  ✓ Фронтенд зібрано")
        return True
    except FileNotFoundError:
        print("  ✗ npm не знайдено. Встанови Node.js.")
        return False


def restart_servers() -> None:
    """Звільнити порти і запустити start_servers.py."""
    print("\n[deploy] Перезапуск серверів...")
    for port in PORTS:
        _free_port(port)
    time.sleep(1.5)

    print("  Запуск Main API + Time Wars...")
    subprocess.Popen(
        [sys.executable, "start_servers.py"],
        cwd=ROOT,
    )
    time.sleep(3)
    print("  ✓ Сервери запущено")
    print("\n  Main API  → http://localhost:8000")
    print("  Time Wars → http://localhost:5174\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Збірка + перезапуск серверів")
    parser.add_argument("--build", action="store_true", help="Зібрати фронтенд")
    parser.add_argument("--restart", action="store_true", help="Перезапустити сервери")
    parser.add_argument("--no-build", action="store_true", help="Перезапуск без збірки (як --restart)")
    args = parser.parse_args()

    do_build = args.build or (not args.restart and not args.no_build)
    do_restart = args.restart or args.no_build or (not args.build and not args.restart and not args.no_build)

    if do_build and not build_frontend():
        sys.exit(1)
    if do_restart:
        restart_servers()


if __name__ == "__main__":
    main()
