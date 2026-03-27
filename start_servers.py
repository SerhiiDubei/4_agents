"""
start_servers.py — Launch both servers simultaneously.

IDEA [REFACTOR: ЗБЕРЕГТИ]: Main 8000 + Time Wars 5174. deploy.py викликає цей скрипт.

Usage:
  python start_servers.py

Starts:
  Main API  → http://localhost:8000  (server/main.py)
  Time Wars → http://localhost:5174  (serve_time_wars.py)

Press Ctrl+C to stop both.
"""

from __future__ import annotations

import subprocess
import sys
import time
import signal
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable

SERVERS = [
    {
        "name": "Main API     (port 8000)",
        "cmd": [PY, "-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"],
    },
    {
        "name": "Time Wars    (port 5174)",
        "cmd": [PY, "serve_time_wars.py", "--port", "5174"],
    },
]

procs: list[subprocess.Popen] = []
restart_counts: list[int] = [0, 0]
MAX_RESTARTS = 5

PORTS = [8000, 5174]


def _free_port(port: int) -> None:
    """Kill ALL processes listening on the given port (Windows + Unix)."""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True
            )
            killed = set()
            for line in result.stdout.splitlines():
                if f":{port} " in line and "LISTENING" in line:
                    parts = line.strip().split()
                    p_id = parts[-1]
                    if p_id not in killed and p_id.isdigit():
                        subprocess.run(["taskkill", "/F", "/PID", p_id],
                                       capture_output=True)
                        killed.add(p_id)
            if killed:
                print(f"  Freed port {port} (PIDs: {', '.join(killed)})")
        else:
            subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True)
    except Exception as e:
        print(f"  Warning: could not free port {port}: {e}")


def shutdown(*_):
    print("\n[start_servers] Shutting down...")
    for p in procs:
        try:
            p.terminate()
        except Exception:
            pass
    for p in procs:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
        except Exception:
            pass
    sys.exit(0)


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

if __name__ == "__main__":
    print("  Freeing ports...")
    for port in PORTS:
        _free_port(port)
    time.sleep(1.5)

    print("=" * 50)
    print("  TIME WARS — Starting all servers")
    print("=" * 50)

    for srv in SERVERS:
        print(f"  Starting: {srv['name']}")
        p = subprocess.Popen(srv["cmd"], cwd=ROOT)
        procs.append(p)
        time.sleep(0.8)

    print()
    print("  Main API  -> http://localhost:8000")
    print("  Time Wars -> http://localhost:5174")
    print("  Frontend  -> http://localhost:5173  (run separately: cd frontend && npm run dev)")
    print()
    print("  Press Ctrl+C to stop all servers")
    print("=" * 50)

    while True:
        for i, (srv, p) in enumerate(zip(SERVERS, procs)):
            ret = p.poll()
            if ret is not None:
                if restart_counts[i] >= MAX_RESTARTS:
                    print(f"\n[start_servers] {srv['name']} crashed {MAX_RESTARTS} times — giving up.")
                    print(f"  Check the command: {' '.join(srv['cmd'])}")
                    continue
                restart_counts[i] += 1
                print(f"\n[start_servers] {srv['name']} exited ({ret}), "
                      f"restarting ({restart_counts[i]}/{MAX_RESTARTS})...")
                # Free port before restart to avoid bind errors
                port = PORTS[i]
                _free_port(port)
                time.sleep(1)
                new_p = subprocess.Popen(srv["cmd"], cwd=ROOT)
                procs[i] = new_p
        time.sleep(3)
