"""
island_routes.py — Island Launcher API routes

GET  /api/island/agents        — list all agents with CORE stats
POST /api/island/run           — SSE stream of simulation output
POST /api/island/human_action  — receive human player's decision
GET  /island                   — serve Island Launcher HTML UI
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
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

_ROOT = Path(__file__).resolve().parent.parent
_AGENTS_DIR = _ROOT / "agents"

router = APIRouter()
_ANSI_RE = re.compile(r"\033\[[0-9;]*[mK]")

# ─── Active simulation state (supports concurrent games) ─────────────────────
# sim_id → {"proc": Popen, "human_event": Event, "human_choice": str|None, "q": Queue}
_active_procs: Dict[str, dict] = {}
_procs_lock = threading.Lock()


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
    human_agent: str = ""   # F2: agent_id that the human controls (empty = all AI)


def _run_sim_in_thread(args: list, env: dict, cwd: str, q: queue.Queue,
                       sim_state: dict):
    """
    Run simulation subprocess in a thread, push lines to queue.

    F2: subprocess stdin=PIPE so server can write human decisions.
    When subprocess prints HUMAN_TURN:{json}, thread sets human_event
    and blocks until human_event is set again (after POST /human_action).
    """
    proc = None
    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,   # F2: bidirectional
            cwd=cwd,
            env=env,
        )
        sim_state["proc"] = proc

        for raw in proc.stdout:
            text = raw.decode("utf-8", errors="replace").rstrip()
            clean = _ANSI_RE.sub("", text)
            if not clean.strip():
                continue

            # F2: intercept HUMAN_TURN lines — pause stdout forwarding until answered
            if clean.startswith("HUMAN_TURN:"):
                q.put(clean)                          # send to SSE so browser shows UI
                ev: threading.Event = sim_state["human_event"]
                ev.clear()
                ev.wait(timeout=120)                  # wait up to 2 min for human choice
                choice = sim_state.get("human_choice") or "cooperate"
                try:
                    proc.stdin.write((choice + "\n").encode("utf-8"))
                    proc.stdin.flush()
                except Exception:
                    pass
                sim_state["human_choice"] = None
            else:
                q.put(clean)

        proc.wait()
    except Exception as e:
        q.put(f"[ERROR] {e}")
    finally:
        q.put(None)  # sentinel — tells SSE generator to stop
        if proc:
            try:
                proc.stdin.close()
            except Exception:
                pass


@router.post("/api/island/run")
async def island_run(req: IslandRunRequest):
    py = sys.executable
    rounds = max(1, min(req.rounds, 20))
    sim_id = str(uuid.uuid4())[:8]

    # -u: unbuffered stdout → every print() streams immediately
    args = [py, "-u", str(_ROOT / "run_simulation_live.py"),
            "--rounds", str(rounds),
            "--sim-id", sim_id]
    if req.agents:
        args += ["--agents", ",".join(req.agents)]
    if req.world_prompt.strip():
        args += ["--world-prompt", req.world_prompt.strip()]
    if req.human_agent.strip():
        args += ["--human-agent", req.human_agent.strip()]   # F2

    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
           "PYTHONUNBUFFERED": "1"}
    q: queue.Queue = queue.Queue()

    sim_state: dict = {
        "proc": None,
        "human_event": threading.Event(),
        "human_choice": None,
        "q": q,
        "sim_id": sim_id,
    }
    sim_state["human_event"].set()   # start in "not-waiting" state

    with _procs_lock:
        _active_procs[sim_id] = sim_state

    t = threading.Thread(
        target=_run_sim_in_thread,
        args=(args, env, str(_ROOT), q, sim_state),
        daemon=True,
    )
    t.start()

    async def _generate():
        loop = asyncio.get_event_loop()
        try:
            while True:
                line = await loop.run_in_executor(None, q.get)
                if line is None:
                    yield f"data: SIM_ID:{sim_id}\n\n"   # send sim_id before DONE
                    yield "data: [DONE]\n\n"
                    break
                safe = line.replace("\n", " ")
                yield f"data: {safe}\n\n"
        finally:
            with _procs_lock:
                _active_procs.pop(sim_id, None)

    # Send sim_id as first event so frontend can target human_action
    async def _generate_with_header():
        yield f"data: SIM_ID:{sim_id}\n\n"
        async for chunk in _generate():
            yield chunk

    return StreamingResponse(
        _generate_with_header(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─── F2: Human player action ──────────────────────────────────────────────────

class HumanActionRequest(BaseModel):
    sim_id: str
    action: str   # "cooperate" | "betray" | "neutral"
    # optional per-target override (future): targets: dict = {}


@router.post("/api/island/human_action")
async def island_human_action(req: HumanActionRequest):
    """
    Receives the human player's decision and unblocks the simulation.
    Called by island_launcher.html when user clicks Cooperate/Betray/Neutral.
    """
    valid = {"cooperate", "betray", "neutral"}
    action = req.action.strip().lower()
    if action not in valid:
        return JSONResponse({"ok": False, "error": f"invalid action '{action}'"}, status_code=400)

    with _procs_lock:
        state = _active_procs.get(req.sim_id)

    if not state:
        return JSONResponse({"ok": False, "error": "sim not found or already finished"}, status_code=404)

    state["human_choice"] = action
    state["human_event"].set()    # unblock _run_sim_in_thread

    return JSONResponse({"ok": True, "sim_id": req.sim_id, "action": action})


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
