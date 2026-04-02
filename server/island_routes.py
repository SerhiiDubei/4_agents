"""
island_routes.py — Island Launcher API routes

GET  /api/island/agents   — list all agents with CORE stats
POST /api/island/run      — SSE stream of simulation output
GET  /island              — serve Island Launcher HTML UI
"""
from __future__ import annotations

import asyncio
import json
import os
import queue
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import List

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

_ROOT = Path(__file__).resolve().parent.parent
_AGENTS_DIR = _ROOT / "agents"

router = APIRouter()
_ANSI_RE = re.compile(r"\033\[[0-9;]*[mK]")


# ─── Agents list ─────────────────────────────────────────────────────────────

@router.get("/api/island/agents")
async def island_agents():
    result = []
    for d in sorted(_AGENTS_DIR.iterdir()):
        core_f = d / "CORE.json"
        if not core_f.exists():
            continue
        try:
            c = json.loads(core_f.read_bytes().decode("utf-8"))
            result.append({
                "id": d.name,
                "name": c.get("name", d.name[-8:]),
                "cooperation_bias": c.get("cooperation_bias", 50),
                "deception_tendency": c.get("deception_tendency", 50),
                "risk_appetite": c.get("risk_appetite", 50),
                "strategic_horizon": c.get("strategic_horizon", 50),
            })
        except Exception:
            pass
    return JSONResponse(result)


# ─── Simulation run via SSE ───────────────────────────────────────────────────

class IslandRunRequest(BaseModel):
    agents: List[str] = []
    rounds: int = 5
    world_prompt: str = ""


def _run_sim_in_thread(args: list, env: dict, cwd: str, q: queue.Queue):
    """Run simulation subprocess in a thread, push lines to queue."""
    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=cwd,
            env=env,
        )
        for raw in proc.stdout:
            text = raw.decode("utf-8", errors="replace").rstrip()
            clean = _ANSI_RE.sub("", text)
            if clean.strip():
                q.put(clean)
        proc.wait()
    except Exception as e:
        q.put(f"[ERROR] {e}")
    finally:
        q.put(None)  # sentinel


@router.post("/api/island/run")
async def island_run(req: IslandRunRequest):
    py = sys.executable
    rounds = max(1, min(req.rounds, 20))

    # -u flag: force unbuffered stdout so every print() streams immediately via SSE
    args = [py, "-u", str(_ROOT / "run_simulation_live.py"), "--rounds", str(rounds)]
    if req.agents:
        args += ["--agents", ",".join(req.agents)]
    if req.world_prompt.strip():
        args += ["--world-prompt", req.world_prompt.strip()]

    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
           "PYTHONUNBUFFERED": "1"}
    q: queue.Queue = queue.Queue()

    t = threading.Thread(target=_run_sim_in_thread, args=(args, env, str(_ROOT), q), daemon=True)
    t.start()

    async def _generate():
        loop = asyncio.get_event_loop()
        while True:
            line = await loop.run_in_executor(None, q.get)
            if line is None:
                yield "data: [DONE]\n\n"
                break
            safe = line.replace("\n", " ")
            yield f"data: {safe}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─── HTML pages ───────────────────────────────────────────────────────────────

@router.get("/island")
async def island_launcher():
    html_path = _ROOT / "island_launcher.html"
    if html_path.exists():
        return FileResponse(html_path, media_type="text/html")
    return HTMLResponse("<h1>island_launcher.html not found</h1>", status_code=404)


@router.get("/hub")
async def hub():
    html_path = _ROOT / "hub.html"
    if html_path.exists():
        return FileResponse(html_path, media_type="text/html")
    return HTMLResponse("<h1>hub.html not found</h1>", status_code=404)
