"""
serve_time_wars.py — Standalone TIME WARS server on port 5174.

Usage:
  python serve_time_wars.py
  python serve_time_wars.py --port 5174

Pages:
  /          — головне меню (СТАРТ / ІСТОРІЯ)
  /game      — live перебіг гри з SSE
  /results   — таблиця всіх минулих сесій

API:
  POST /api/start-game          — запустити нову гру
  GET  /api/game-events/{id}    — SSE stream подій
  GET  /api/time-wars-summary   — JSON список сесій
  GET  /logs/*                  — статичні HTML звіти
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
LOGS_ROOT = ROOT / "logs"           # root for static serving
LOGS_DIR = LOGS_ROOT / "time_wars"  # time_wars JSONL + HTML lives here
LOGS_ROOT.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
ROSTER_PATH = ROOT / "agents" / "roster.json"

_TW_PATTERN = re.compile(r"time_wars_(tw_\d+)_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})\.jsonl")

# In-memory store: session_id → list of events (populated after game runs)
_sessions_store: dict[str, list[dict]] = {}
_sessions_status: dict[str, str] = {}   # "running" | "done" | "error"
_sessions_html: dict[str, str] = {}     # session_id → /logs/time_wars_*.html path
_sessions_progress: dict[str, dict] = {}  # session_id → {round, tick, active} for SSE progress
_sessions_live_events: dict[str, list[dict]] = {}  # stream events in real-time; append each round
_sessions_last_flush: dict[str, int] = {}  # session_id -> last flushed event_log index

# Logging: always print to stderr so user sees TW activity (incl. LLM calls)
def _tw_log(msg: str) -> None:
    print(f"[TW] {msg}", flush=True, file=sys.stderr)

# Human player support
_sessions_human: dict[str, bool] = {}          # session_id → has human slot
_sessions_user_token: dict[str, str] = {}       # session_id → JWT token
_human_pending: dict[str, dict] = {}            # session_id → {tick: threading.Event}
_human_actions: dict[str, dict] = {}            # session_id → {tick: action_dict}

ROLE_NAMES: dict[str, str] = {
    "role_snake": "Змій",
    "role_peacekeeper": "Миротворець",
    "role_banker": "Банкір",
    "role_gambler": "Авантюрист",
}


def _flush_events_to_live(session_id: str, session: "Session") -> None:
    """Append new enriched events to _sessions_live_events for real-time SSE streaming."""
    last = _sessions_last_flush.get(session_id, 0)
    new_events = session.event_log[last:]
    if not new_events:
        return
    agent_display = _load_agent_names()
    for ev in new_events:
        e = dict(ev)
        for field in ("agent_id", "actor_id", "target_id", "winner_id"):
            if field in e and e[field]:
                e[f"{field}_name"] = agent_display.get(e[field], e[field])
        if "final_times" in e:
            e["final_times_named"] = {agent_display.get(k, k): v for k, v in e["final_times"].items()}
        if "roles" not in e and ev.get("event_type") == "role_assignment":
            e["role_name"] = ROLE_NAMES.get(e.get("role_id", ""), e.get("role_id", ""))
        _sessions_live_events.setdefault(session_id, []).append(e)
    _sessions_last_flush[session_id] = len(session.event_log)

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
    import uvicorn
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "fastapi", "uvicorn[standard]"])
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
    import uvicorn


app = FastAPI(title="TIME WARS", docs_url=None, redoc_url=None)

try:
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # island_launcher + hub connect from any origin
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
except Exception:
    pass

# Simple in-memory rate limiter for /auth-like endpoints
import collections
_rate_limit_store: dict[str, list[float]] = collections.defaultdict(list)

def _check_rate_limit(key: str, max_calls: int = 10, window_sec: float = 60.0) -> bool:
    """Returns True if under limit, False if exceeded."""
    now = time.time()
    calls = _rate_limit_store[key]
    _rate_limit_store[key] = [t for t in calls if now - t < window_sec]
    if len(_rate_limit_store[key]) >= max_calls:
        return False
    _rate_limit_store[key].append(now)
    return True


# ── helpers ────────────────────────────────────────────────────────────────

def _load_agent_names() -> dict[str, str]:
    names: dict[str, str] = {}
    if ROSTER_PATH.exists():
        try:
            for a in json.loads(ROSTER_PATH.read_text(encoding="utf-8")).get("agents", []):
                if a.get("id") and a.get("name"):
                    names[a["id"]] = a["name"]
        except Exception:
            pass
    return names


def _load_roster_agents() -> list[str]:
    if not ROSTER_PATH.exists():
        return []
    try:
        data = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))
        agents = data.get("agents", [])
        count = data.get("default_count", 4)
        return [a["id"] for a in agents[:count] if a.get("id")]
    except Exception:
        return []


def _parse_tw_jsonl(path: Path) -> dict | None:
    game_start: dict = {}
    game_over: dict = {}
    roles: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            et = ev.get("event_type", "")
            if et == "game_start":
                game_start = ev
            elif et == "role_assignment":
                roles[ev.get("agent_id", "")] = ev.get("role_id", "")
            elif et == "game_over":
                game_over = ev
    except Exception:
        return None
    return {"game_start": game_start, "game_over": game_over, "roles": roles} if game_over else None


def _get_sessions() -> list[dict]:
    if not LOGS_DIR.exists():
        return []
    agent_display = _load_agent_names()
    paths = sorted(
        [f for f in LOGS_DIR.glob("time_wars_*.jsonl") if _TW_PATTERN.match(f.name)],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    sessions = []
    for path in paths:
        m = _TW_PATTERN.match(path.name)
        if not m:
            continue
        session_id, date_str, time_str = m.group(1), m.group(2), m.group(3)
        parsed = _parse_tw_jsonl(path)
        if not parsed:
            continue
        go = parsed["game_over"]
        final_times: dict[str, int] = go.get("final_times", {})
        winner_id: str = go.get("winner_id", "")
        scores_by_name = {agent_display.get(aid, aid): t for aid, t in final_times.items()}
        survivor_count = sum(1 for t in final_times.values() if t > 0)
        html_path = path.with_suffix(".html")
        has_report = html_path.exists()
        sessions.append({
            "sessionId": session_id,
            "playedAt": f"{date_str} {time_str.replace('-', ':')}",
            "winner": agent_display.get(winner_id, winner_id),
            "finalTimes": scores_by_name,
            "roles": {agent_display.get(aid, aid): ROLE_NAMES.get(rid, rid) for aid, rid in parsed["roles"].items()},
            "reportPath": f"/logs/time_wars/{path.name.replace('.jsonl', '.html')}" if has_report else None,
            "tick": go.get("tick", 0),
            "survivorCount": survivor_count,
            "totalPlayers": len(final_times),
        })
    return sessions


# ── game runner ────────────────────────────────────────────────────────────

def _run_game_in_thread(session_id: str) -> None:
    """Run one TIME WARS session synchronously in a background thread."""
    _tw_log(f"Thread started for session {session_id}")
    _sessions_status[session_id] = "running"
    _sessions_store[session_id] = []
    try:
        sys.path.insert(0, str(ROOT))
        from game_modes.time_wars.state import create_session, save_trust_to_memory
        from game_modes.time_wars.loop import (
            tick, escalating_drain, apply_cooperate, apply_steal, apply_code_use,
            run_storm, run_crisis, apply_game_end_bonuses,
            is_game_over, log_game_start, log_game_over, log_code_buy,
            build_situation_text, log_round_start, log_player_intent,
            run_code_phase, apply_mana_per_round,
        )
        from game_modes.time_wars.agent_context import get_agent_action_mock
        from game_modes.time_wars.logging_export import write_session_log
        from game_modes.time_wars.shop import load_codes, get_available_codes, buy_code, effective_cost
        from game_modes.time_wars.log_to_html import generate_time_wars_html

        agent_ids = _load_roster_agents() or ["agent_synth_g", "agent_synth_c", "agent_synth_d", "agent_synth_h"]
        # If human slot requested, designate the last agent_id as the human player
        has_human = _sessions_human.get(session_id, False)
        human_agent_id = agent_ids[-1] if has_human else None

        # Battle royale config:
        # - base_sec per player: enough time to survive ~30 ticks of escalating drain
        # - duration cap: high enough that the game always ends by elimination, not timeout
        # - drain doubles every DRAIN_DOUBLE_EVERY ticks → guaranteed last-one-standing
        base_sec = 1000
        DRAIN_DOUBLE_EVERY = 50   # doubles every 5 rounds → elimination guaranteed ~round 20-25
        DRAIN_BASE = 3            # drain_base=3: coop (+30) = drain (3×10=30) → zero net, steals create spread
        ticks_per_action = 10          # action round every 10 ticks
        duration = 999_999             # effectively unlimited; elimination guaranteed by escalating drain
        min_ticks = ticks_per_action
        storm_after_ticks = 300        # storm at round 30 (tick 300) — mid/late game
        rng = random.Random()

        _tw_log(f"Session {session_id} starting... agents={agent_ids}")
        t_session_start = time.perf_counter()
        session = create_session(
            session_id=session_id,
            agent_ids=agent_ids,
            base_seconds_per_player=base_sec,
            duration_limit_sec=duration,
        )
        log_game_start(session, drain_double_every=DRAIN_DOUBLE_EVERY)
        _sessions_live_events[session_id] = []
        _sessions_last_flush[session_id] = 0
        _flush_events_to_live(session_id, session)
        _tw_log(f"Session created in {time.perf_counter() - t_session_start:.2f}s")
        _sessions_progress[session_id] = {"round": 0, "tick": 0, "active": len(agent_ids)}

        # ── MCS: init NPC mood states ────────────────────────────────────────
        _mcs_ok = False
        _mcs_states: dict[str, Any] = {}
        _mcs_engine: Any = None
        _mcs_processor: Any = None
        _openrouter_key = ""
        try:
            import os as _os
            from simulation.mcs.state import NpcState as _NpcState
            from simulation.mcs.world_engine import WorldEngine as _WorldEngine, WorldConfig as _WorldConfig
            from simulation.mcs.tick_processor import TickProcessor as _TickProcessor
            _openrouter_key = _os.environ.get("OPENROUTER_API_KEY", "")
            _mcs_engine = _WorldEngine(_WorldConfig(agents=list(agent_ids)))
            _mcs_processor = _TickProcessor(llm_interval=10)
            for _aid in agent_ids:
                _core_p = ROOT / "agents" / _aid / "CORE.json"
                _soul_p = ROOT / "agents" / _aid / "SOUL.md"
                if _core_p.exists():
                    _core_d = json.loads(_core_p.read_text(encoding="utf-8"))
                    _soul_d = _soul_p.read_text(encoding="utf-8") if _soul_p.exists() else ""
                    _mcs_states[_aid] = _NpcState.from_soul_and_core(_aid, _soul_d, _core_d)
            _mcs_ok = bool(_mcs_states)
            _tw_log(f"MCS initialized: {len(_mcs_states)} agent mood states")
        except Exception as _mcs_init_err:
            _tw_log(f"MCS init skipped (non-fatal): {_mcs_init_err}")

        codes_catalog = load_codes()
        _tw_log("Entering main game loop...")

        current_round_num = 0  # updated each action phase
        for t in range(1, duration + 1):
            if t <= 3 or t % 50 == 0:
                _tw_log(f"Tick {t}...")
            drain = escalating_drain(t, base=DRAIN_BASE, double_every=DRAIN_DOUBLE_EVERY)
            eliminated = tick(session, t, drain_sec=drain)

            # Per-tick progress: player times for real-time UI (lightweight, no flush overhead)
            _sessions_progress[session_id] = {
                "round": current_round_num,
                "tick": t,
                "tick_total": duration,
                "drain": drain,
                "active": len(session.active_players()),
                "players": [
                    {
                        "id": p.agent_id,
                        "time": p.time_remaining_sec,
                        "mana": p.mana,
                        "status": p.status,
                    }
                    for p in session.players
                ],
            }

            # Check after tick (eliminations may have resolved the battle royale)
            if is_game_over(session, t, min_ticks):
                apply_game_end_bonuses(session, t)
                active = session.active_players()
                if len(active) == 1:
                    winner = active[0].agent_id
                elif len(active) == 0:
                    # Tie: all remaining players hit 0 on same tick → give win to highest mana
                    winner_p = max(session.players, key=lambda p: p.mana)
                    winner = winner_p.agent_id
                else:
                    winner = None
                log_game_over(session, t, winner_id=winner)
                _tw_log(f"Game over at tick {t} | winner={winner} | total session time: {time.perf_counter() - t_session_start:.1f}s")
                break

            # Action phase every ticks_per_action ticks
            if t % ticks_per_action == 0:
                round_num = t // ticks_per_action
                t_round_start = time.perf_counter()
                current_round_num = round_num
                sit = build_situation_text(session, threshold_sec=max(60, base_sec // 3))
                _log_extra = {"drain_sec": drain, "drain_double_every": DRAIN_DOUBLE_EVERY}
                log_round_start(session, round_num, t, t, {**sit, **_log_extra})
                apply_mana_per_round(session, t)
                _tw_log(f"Round {round_num} (tick {t}) | drain={drain}s | active={len(session.active_players())}")

                # ── MCS: mood tick (Level 1 math, Level 2 background LLM) ──
                if _mcs_ok and _mcs_engine and _mcs_states:
                    for _p in session.active_players():
                        _mid = _p.agent_id
                        if _mid not in _mcs_states:
                            continue
                        _mcs_ev = _mcs_engine.next_event(_mid)
                        _mcs_states[_mid], _mdelta = _mcs_processor.tick_level1(
                            _mcs_states[_mid], _mcs_ev
                        )
                        _mst = _mcs_states[_mid]
                        session.event_log.append({
                            "event_type": "mcs_mood",
                            "round_num": round_num,
                            "tick": t,
                            "agent_id": _mid,
                            "energy": round(_mst.mood.energy, 2),
                            "fear": round(_mst.mood.fear, 2),
                            "tension": round(_mst.mood.tension, 2),
                            "persona": _mst.personas.dominant(),
                            "delta": _mdelta.value,
                        })
                        # Level 2: fire-and-forget LLM reflection in daemon thread
                        if _openrouter_key and _mst.needs_llm(_mcs_processor.llm_interval):
                            def _run_l2(_s=_mcs_states[_mid], _aid=_mid):
                                try:
                                    _updated = _mcs_processor.tick_level2(
                                        _s, ROOT / "agents", _openrouter_key
                                    )
                                    _mcs_states[_aid] = _updated
                                except Exception:
                                    pass
                            threading.Thread(target=_run_l2, daemon=True).start()

                # ── SHOP phase: buy as many codes as mana allows ──────────
                t_shop = time.perf_counter()
                _tw_log("  SHOP phase...")
                if codes_catalog:
                    for p in session.active_players():
                        bought = 0
                        while bought < 6:  # safety cap per round
                            available = get_available_codes(session, p.agent_id, codes_catalog)
                            if not available:
                                break
                            # Prefer self/steal codes when in danger, give codes when rich
                            my_ratio = p.time_remaining_sec / base_sec
                            if my_ratio < 0.4:
                                pref_types = ["self", "steal", "gamble"]
                            elif my_ratio > 0.7:
                                pref_types = ["give", "plus_all_except_one", "steal"]
                            else:
                                pref_types = []
                            preferred = [c for c in available if c.get("type") in pref_types] if pref_types else []
                            card = rng.choice(preferred) if preferred else rng.choice(available)
                            cost = effective_cost(card, session, p.agent_id)
                            if p.mana < cost:
                                break
                            if buy_code(session, p.agent_id, card["id"], codes_catalog):
                                log_code_buy(session, p.agent_id, card["id"], cost, t)
                                bought += 1
                            else:
                                break
                _tw_log(f"  SHOP done in {time.perf_counter() - t_shop:.2f}s")

                # ── CODE phase: use codes from inventory (utility-based) ──
                t_code = time.perf_counter()
                run_code_phase(session, t, rng=rng)
                _tw_log(f"  CODE done in {time.perf_counter() - t_code:.2f}s")

                # ── COMM phase: LLM dialog (public + DM) ─────────────────
                round_messages: list[dict] = []
                t_comm = time.perf_counter()
                try:
                    from pathlib import Path as _Path
                    from simulation.dialog_engine import generate_round_dialog_flat
                    agent_display = _load_agent_names()
                    agents_root = ROOT / "agents"
                    agent_cfgs = []
                    for p in session.active_players():
                        soul_path = agents_root / p.agent_id / "SOUL.md"
                        states_path = agents_root / p.agent_id / "STATES.md"
                        mem_path = agents_root / p.agent_id / "MEMORY.json"
                        core_path = agents_root / p.agent_id / "CORE.json"
                        soul_md = soul_path.read_text(encoding="utf-8") if soul_path.exists() else ""
                        states_md = states_path.read_text(encoding="utf-8") if states_path.exists() else ""
                        mem_data = json.loads(mem_path.read_text(encoding="utf-8")) if mem_path.exists() else {}
                        core_data = json.loads(core_path.read_text(encoding="utf-8")) if core_path.exists() else {}
                        # Choose DM target: agent we trust least (most likely to betray)
                        others_sorted = sorted(
                            [o for o in session.active_players() if o.agent_id != p.agent_id],
                            key=lambda o: session.get_trust(p.agent_id, o.agent_id)
                        )
                        dm_target = others_sorted[0].agent_id if others_sorted else None
                        agent_cfgs.append({
                            "agent_id": p.agent_id,
                            "soul_md": soul_md,
                            "states_md": states_md,
                            "memory_summary": mem_data,
                            "deception_tendency": float(core_data.get("deception_tendency", 30)),
                            "model": core_data.get("model", "google/gemini-2.0-flash-001"),
                            "dm_target": dm_target,
                            "game_context": (
                                f"Time Wars round {round_num}. "
                                f"My time: {p.time_remaining_sec}s. "
                                f"Drain: {drain}s/tick. "
                                f"Players left: {len(session.active_players())}."
                            ),
                        })
                    if agent_cfgs:
                        _tw_log(f"  COMM phase (LLM): {len(agent_cfgs)} agents, public+DM calls...")
                        # ROB-1: retry up to 2 times on LLM failure; ROB-2: 90s timeout per attempt
                        _comm_rd = None
                        for _attempt in range(3):
                            try:
                                import signal as _signal
                                import threading as _th

                                _result_holder: list = []
                                _err_holder: list = []

                                def _run_dialog():
                                    try:
                                        _result_holder.append(generate_round_dialog_flat(
                                            round_number=round_num,
                                            agent_configs=agent_cfgs,
                                            agent_names=agent_display,
                                            verbose=True,
                                        ))
                                    except Exception as _e:
                                        _err_holder.append(_e)

                                _t = _th.Thread(target=_run_dialog, daemon=True)
                                _t.start()
                                _t.join(timeout=90)  # ROB-2: 90s timeout

                                if _result_holder:
                                    _comm_rd = _result_holder[0]
                                    break
                                elif _err_holder:
                                    _tw_log(f"  COMM LLM attempt {_attempt+1} error: {_err_holder[0]}")
                                else:
                                    _tw_log(f"  COMM LLM attempt {_attempt+1} timed out (90s)")
                                if _attempt < 2:
                                    time.sleep(2 ** _attempt)  # backoff: 1s, 2s
                            except Exception as _retry_err:
                                _tw_log(f"  COMM retry wrapper error: {_retry_err}")
                                break

                        rd = _comm_rd
                        if rd is None:
                            _tw_log("  COMM phase skipped (all attempts failed/timed out)")
                        round_messages = [m.to_dict() for m in rd.messages] if rd else []
                        # Trust update from dialog tone
                        _support_kws = ["підтримую", "допоможу", "за тебе", "союзник", "довіряю", "разом ми", "покладайся", "я з тобою"]
                        for msg in (rd.messages if rd else []):
                            msg_text = (getattr(msg, "text", "") or "").lower()
                            if msg.is_deceptive:
                                for p2 in session.active_players():
                                    if p2.agent_id != msg.sender_id:
                                        old = session.get_trust(p2.agent_id, msg.sender_id)
                                        session.set_trust(p2.agent_id, msg.sender_id, max(0, old - 0.05))
                            # Support mechanic: supportive public/DM messages boost trust
                            elif any(kw in msg_text for kw in _support_kws):
                                ch = getattr(msg, "channel", "public")
                                trust_boost = 0.06 if ch.startswith("dm_") else 0.03
                                target_id = ch.replace("dm_", "") if ch.startswith("dm_") else None
                                for p2 in session.active_players():
                                    if p2.agent_id == msg.sender_id:
                                        continue
                                    if target_id and p2.agent_id != target_id:
                                        continue
                                    old = session.get_trust(p2.agent_id, msg.sender_id)
                                    session.set_trust(p2.agent_id, msg.sender_id, min(1.0, old + trust_boost))
                        # Emit comm events to SSE stream
                        for msg in round_messages:
                            session.event_log.append({
                                "event_type": "comm_message",
                                "round_num": round_num,
                                "tick": t,
                                "sender_id": msg.get("sender", ""),
                                "channel": msg.get("channel", "public"),
                                "text": msg.get("text", ""),
                                "sender_id_name": agent_display.get(msg.get("sender", ""), msg.get("sender", "")),
                            })
                except Exception as _comm_err:
                    _tw_log(f"  COMM phase ERROR: {_comm_err}")
                _tw_log(f"  COMM done in {time.perf_counter() - t_comm:.2f}s")

                # ── ACTION phase: cooperate / steal / pass ────────────────
                t_action = time.perf_counter()
                for p in session.active_players():
                    if has_human and p.agent_id == human_agent_id:
                        evt = threading.Event()
                        if session_id not in _human_pending:
                            _human_pending[session_id] = {}
                        _human_pending[session_id][t] = evt
                        got_action = evt.wait(timeout=60)
                        human_act_raw = _human_actions.get(session_id, {}).get(t) if got_action else None
                        if human_act_raw:
                            act = {
                                "action": human_act_raw.get("action", "pass"),
                                "target_id": human_act_raw.get("target_id") or None,
                                "code_index": None,
                                "thought": "Player decides",
                                "plan": human_act_raw.get("action", "pass"),
                                "choice": human_act_raw.get("action", "pass"),
                                "reason": "Human decision",
                            }
                        else:
                            act = {"action": "pass", "target_id": None, "code_index": None,
                                   "thought": "Timeout", "plan": "Pass", "choice": "Pass", "reason": "Timeout"}
                    else:
                        act = get_agent_action_mock(
                            session, p.agent_id, rng=rng, last_messages=round_messages,
                            agent_names=agent_display, agents_root=ROOT / "agents",
                            round_num=round_num, total_rounds=max(20, duration // ticks_per_action),
                            current_tick=t, ticks_per_action=ticks_per_action,
                        )

                    log_player_intent(
                        session, p.agent_id, t,
                        thought=act.get("thought", ""),
                        plan=act.get("plan", ""),
                        choice=act.get("choice", ""),
                        reason=act.get("reason", ""),
                    )
                    if act["action"] == "cooperate" and act["target_id"]:
                        apply_cooperate(session, p.agent_id, act["target_id"], t)
                    elif act["action"] == "steal" and act["target_id"]:
                        apply_steal(session, p.agent_id, act["target_id"], t, rng=rng)
                _tw_log(f"  ACTION done in {time.perf_counter() - t_action:.2f}s | round total: {time.perf_counter() - t_round_start:.2f}s")
                _flush_events_to_live(session_id, session)

            # Late-game storm
            if t == storm_after_ticks:
                run_storm(session, t, delta_sec=-20)

            # Second pass: check after actions too
            if is_game_over(session, t, min_ticks):
                apply_game_end_bonuses(session, t)
                active = session.active_players()
                if len(active) == 1:
                    winner = active[0].agent_id
                elif len(active) == 0:
                    winner_p = max(session.players, key=lambda p: p.mana)
                    winner = winner_p.agent_id
                else:
                    winner = None
                log_game_over(session, t, winner_id=winner)
                _tw_log(f"Game over at tick {t} | winner={winner} | total: {time.perf_counter() - t_session_start:.1f}s")
                break
        else:
            # Hard cap reached — declare winner by most time remaining
            apply_game_end_bonuses(session, duration)
            active = session.active_players()
            winner = max(active, key=lambda x: x.time_remaining_sec).agent_id if active else None
            log_game_over(session, duration, winner_id=winner)
            _tw_log(f"Game hard cap at tick {duration} | winner={winner} | total: {time.perf_counter() - t_session_start:.1f}s")

        # Persist final trust back to agents' MEMORY.json
        try:
            save_trust_to_memory(session)
        except Exception:
            pass

        LOGS_DIR.mkdir(exist_ok=True)
        path = write_session_log(session, LOGS_DIR)
        html_path = generate_time_wars_html(path)
        _sessions_html[session_id] = f"/logs/time_wars/{html_path.name}"

        # Flush any remaining events (e.g. log_game_over) for real-time SSE
        _flush_events_to_live(session_id, session)
        # Inject display names into events for frontend (also keep full store for backwards compat)
        agent_display = _load_agent_names()
        enriched = []
        for ev in session.event_log:
            e = dict(ev)
            for field in ("agent_id", "actor_id", "target_id", "winner_id"):
                if field in e and e[field]:
                    e[f"{field}_name"] = agent_display.get(e[field], e[field])
            if "final_times" in e:
                e["final_times_named"] = {agent_display.get(k, k): v for k, v in e["final_times"].items()}
            if "roles" not in e and ev.get("event_type") == "role_assignment":
                e["role_name"] = ROLE_NAMES.get(e.get("role_id", ""), e.get("role_id", ""))
            enriched.append(e)
        _sessions_store[session_id] = enriched
        _sessions_status[session_id] = "done"
        _tw_log(f"Game complete: {len(enriched)} events ready for SSE")

        # Persist to database
        _save_session_to_db(session_id, session, enriched, _sessions_html.get(session_id, ""))

    except Exception as exc:
        import traceback
        _tw_log(f"Game thread ERROR for {session_id}: {exc}")
        _tw_log(traceback.format_exc())
        _sessions_store[session_id] = [{"event_type": "error", "message": str(exc), "trace": traceback.format_exc()}]
        _sessions_status[session_id] = "error"


def _save_session_to_db(session_id: str, session: "Session", enriched_events: list, report_path: str) -> None:
    """Write completed game session and all player actions to the database."""
    try:
        from db.database import SessionLocal
        from db.models import GameSession as DbGameSession, PlayerAction
        import json as _json
        from datetime import datetime

        db = SessionLocal()
        try:
            game_over = next((e for e in enriched_events if e.get("event_type") == "game_over"), {})
            round_starts = [e for e in enriched_events if e.get("event_type") == "round_start"]
            total_rounds = len(round_starts)
            total_ticks = game_over.get("tick", 0)
            winner_id = game_over.get("winner_id", "")

            existing = db.query(DbGameSession).filter(DbGameSession.session_id == session_id).first()
            if not existing:
                gs = DbGameSession(
                    id=str(__import__("uuid").uuid4()),
                    session_id=session_id,
                    ended_at=datetime.utcnow(),
                    winner_id=winner_id,
                    rounds=total_rounds,
                    ticks=total_ticks,
                    base_sec=session.base_seconds_per_player,
                    drain_base=3,
                    drain_double_every=200,
                    report_path=report_path,
                    has_human_player=False,
                )
                db.add(gs)
                db.flush()

                # Write player actions (steal/cooperate only)
                for ev in enriched_events:
                    et = ev.get("event_type")
                    if et in ("steal", "cooperate", "code_use", "pass"):
                        if ev.get("target_effect"):
                            continue   # skip target-side steal duplicate
                        pa = PlayerAction(
                            id=str(__import__("uuid").uuid4()),
                            session_id=session_id,
                            tick=ev.get("tick", 0),
                            actor_id=ev.get("actor_id", ev.get("agent_id", "")),
                            action_type=et,
                            target_id=ev.get("target_id"),
                            delta_sec=ev.get("time_delta_seconds"),
                            outcome=ev.get("outcome"),
                            roll=ev.get("roll"),
                        )
                        db.add(pa)

                db.commit()
        finally:
            db.close()
    except Exception as db_exc:
        import traceback as tb
        print(f"[DB] Failed to save session {session_id}: {db_exc}\n{tb.format_exc()}")


# ── API ────────────────────────────────────────────────────────────────────

class StartGameRequest(BaseModel):
    human_slot: bool = False      # True = one agent slot is reserved for a human player
    user_token: str = ""          # optional JWT to link human decisions to a user account


@app.post("/api/start-game")
async def start_game(request: Request, body: StartGameRequest = None):
    body = body or StartGameRequest()
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(f"start:{client_ip}", max_calls=5, window_sec=60):
        raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
    session_id = f"tw_{int(time.time())}"
    _sessions_human[session_id] = body.human_slot
    _sessions_user_token[session_id] = body.user_token
    # Human decision queue: pending tick → action will be submitted via /api/human-action
    if body.human_slot:
        _human_pending[session_id] = {}  # tick → asyncio.Event
        _human_actions[session_id] = {}  # tick → {"action": ..., "target_id": ...}
    t = threading.Thread(target=_run_game_in_thread, args=(session_id,), daemon=True)
    t.start()
    return JSONResponse({"sessionId": session_id, "humanSlot": body.human_slot})


@app.get("/api/game-status/{session_id}")
async def game_status(session_id: str):
    status = _sessions_status.get(session_id, "unknown")
    count = len(_sessions_store.get(session_id, []))
    return JSONResponse({"status": status, "eventCount": count, "reportPath": _sessions_html.get(session_id)})


class HumanActionRequest(BaseModel):
    tick: int
    action: str        # "cooperate" | "steal" | "pass"
    target_id: str = ""


@app.post("/api/human-action/{session_id}")
async def submit_human_action(session_id: str, body: HumanActionRequest):
    """Called by the human player UI to submit their action for a given tick."""
    if not _sessions_human.get(session_id):
        raise HTTPException(status_code=400, detail="This session has no human player slot")
    if _sessions_status.get(session_id) not in ("running", "done"):
        raise HTTPException(status_code=400, detail="Session not running")

    # Store the action and signal the game thread
    if session_id not in _human_actions:
        _human_actions[session_id] = {}
    if session_id not in _human_pending:
        _human_pending[session_id] = {}

    _human_actions[session_id][body.tick] = {
        "action": body.action,
        "target_id": body.target_id,
    }
    # Signal the waiting game thread
    evt = _human_pending[session_id].get(body.tick)
    if evt:
        evt.set()

    # Save to DB if user is authenticated
    token = _sessions_user_token.get(session_id, "")
    if token:
        try:
            from db.database import SessionLocal
            from db.models import HumanDecision
            from db.auth import decode_token
            import json as _json
            payload = decode_token(token)
            if payload:
                db = SessionLocal()
                try:
                    hd = HumanDecision(
                        id=str(__import__("uuid").uuid4()),
                        user_id=payload["sub"],
                        session_id=session_id,
                        tick=body.tick,
                        action_type=body.action,
                        target_id=body.target_id or None,
                        context_json=None,
                    )
                    db.add(hd)
                    db.commit()
                finally:
                    db.close()
        except Exception as e:
            print(f"[DB] human decision save failed: {e}")

    return JSONResponse({"ok": True, "tick": body.tick, "action": body.action})


@app.get("/api/pending-action/{session_id}")
async def pending_action(session_id: str):
    """Returns which tick is currently waiting for human input (if any)."""
    pending = _human_pending.get(session_id, {})
    waiting = [tick for tick, evt in pending.items() if not evt.is_set()]
    return JSONResponse({"waitingTick": waiting[0] if waiting else None})


@app.get("/api/game-events/{session_id}")
async def game_events(session_id: str):
    """SSE stream: real-time events from _sessions_live_events, progress updates, then __stream_end__."""
    _tw_log(f"SSE client connected for {session_id}")

    async def event_stream():
        # Stream events in real-time from _sessions_live_events (flushed each round)
        yielded_count = 0
        last_progress = {}
        for i in range(1200):  # 1200 * 0.5s = 600s = 10 min
            status = _sessions_status.get(session_id, "unknown")
            live = _sessions_live_events.get(session_id, [])

            # Yield any new events immediately (game_start arrives after first flush)
            while yielded_count < len(live):
                ev = live[yielded_count]
                yielded_count += 1
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                et = ev.get("event_type", "")
                if et in ("round_start", "game_over"):
                    await asyncio.sleep(0.9)
                else:
                    await asyncio.sleep(0.05)

            progress = _sessions_progress.get(session_id, {})
            if progress != last_progress:
                last_progress = dict(progress)
                yield f"data: {json.dumps({'event_type': '__progress__', 'round': progress.get('round', 0), 'tick': progress.get('tick', 0), 'active': progress.get('active', 0)}, ensure_ascii=False)}\n\n"

            if status in ("done", "error"):
                _tw_log(f"SSE: game {status} for {session_id}")
                break
            await asyncio.sleep(0.5)

        # Yield any remaining events (flushed when game ended)
        live = _sessions_live_events.get(session_id, [])
        while yielded_count < len(live):
            ev = live[yielded_count]
            yielded_count += 1
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            et = ev.get("event_type", "")
            if et in ("round_start", "game_over"):
                await asyncio.sleep(0.9)
            else:
                await asyncio.sleep(0.05)

        report = _sessions_html.get(session_id)
        yield f"data: {json.dumps({'event_type': '__stream_end__', 'reportPath': report}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@app.get("/api/time-wars-summary")
async def time_wars_summary():
    sessions = _get_sessions()
    agent_totals: dict[str, int] = {}
    agent_appearances: dict[str, int] = {}  # how many sessions each agent appeared in
    for s in sessions:
        for name, val in s["finalTimes"].items():
            agent_totals[name] = agent_totals.get(name, 0) + val
            agent_appearances[name] = agent_appearances.get(name, 0) + 1
    # Sort agents by number of appearances (most frequent first)
    agent_names = sorted(agent_appearances.keys(), key=lambda n: -agent_appearances[n])
    return JSONResponse({"sessions": sessions, "agentTotals": agent_totals, "agentNames": agent_names})


@app.get("/api/time-wars-count")
async def time_wars_count():
    if not LOGS_DIR.exists():
        return JSONResponse({"count": 0})
    count = sum(1 for f in LOGS_DIR.glob("time_wars_*.jsonl") if _TW_PATTERN.match(f.name))
    return JSONResponse({"count": count})


# ── Pages ──────────────────────────────────────────────────────────────────

_CSS_BASE = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #050c14; color: #e2e8f0; font-family: 'Segoe UI', system-ui, sans-serif; min-height: 100vh; }
a { color: inherit; text-decoration: none; }
.btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px; padding: 14px 28px; border-radius: 10px; font-size: 1rem; font-weight: 700; cursor: pointer; border: none; transition: all .15s; letter-spacing: .05em; }
.btn:hover { filter: brightness(1.15); transform: translateY(-1px); }
.btn:active { transform: translateY(0); }
.btn-green { background: #16a34a; color: #fff; }
.btn-slate { background: #334155; color: #e2e8f0; }
.btn-purple { background: #7c3aed; color: #fff; }
.btn-sm { padding: 6px 14px; font-size: .8rem; border-radius: 6px; }
"""


@app.get("/", response_class=HTMLResponse)
async def main_menu():
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="uk">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TIME WARS</title>
  <style>
    {_CSS_BASE}
    body {{ display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; padding: 40px 20px; }}
    .logo {{ font-size: clamp(2.5rem, 8vw, 5rem); font-weight: 900; letter-spacing: .15em; color: #4ade80; text-shadow: 0 0 40px rgba(74,222,128,.35); margin-bottom: 12px; }}
    .tagline {{ color: #64748b; font-size: 1rem; letter-spacing: .1em; margin-bottom: 56px; text-align: center; }}
    .menu {{ display: flex; flex-direction: column; gap: 16px; width: 100%; max-width: 340px; }}
    .btn-start {{ font-size: 1.25rem; padding: 20px 32px; background: linear-gradient(135deg, #16a34a, #22c55e); box-shadow: 0 4px 24px rgba(34,197,94,.3); border-radius: 12px; }}
    .btn-history {{ font-size: 1rem; padding: 16px 32px; background: #1e293b; color: #94a3b8; border: 1px solid #334155; border-radius: 12px; }}
    .btn-history:hover {{ background: #273549; color: #e2e8f0; }}
    #status {{ margin-top: 20px; font-size: .9rem; color: #4ade80; min-height: 24px; text-align: center; }}
    .count-badge {{ font-size: .8rem; background: #1e293b; color: #64748b; padding: 4px 10px; border-radius: 20px; margin-top: 8px; }}
  </style>
</head>
<body>
  <div class="logo">TIME WARS</div>
  <p class="tagline">Час — ресурс. Хто збереже більше — переможе.</p>
  <div id="count-wrap"><span class="count-badge" id="count-badge">Завантаження...</span></div>
  <div class="menu" style="margin-top:24px;">
    <button class="btn btn-start" id="btn-start" onclick="startGame()">▶ СТАРТ ГРИ</button>
    <a href="/results" class="btn btn-history">📋 ІСТОРІЯ ІГОР</a>
  </div>
  <div id="status"></div>
  <script>
    fetch('/api/time-wars-count')
      .then(r => r.json())
      .then(d => document.getElementById('count-badge').textContent = d.count + ' зіграних сесій')
      .catch(() => document.getElementById('count-badge').textContent = '');

    async function startGame() {{
      const btn = document.getElementById('btn-start');
      btn.disabled = true;
      btn.textContent = '⏳ Запускаю...';
      document.getElementById('status').textContent = 'Підготовка гри...';
      try {{
        const r = await fetch('/api/start-game', {{ method: 'POST' }});
        const d = await r.json();
        if (d.sessionId) {{
          window.location.href = '/game?session=' + d.sessionId;
        }} else {{
          throw new Error('No sessionId');
        }}
      }} catch(e) {{
        document.getElementById('status').textContent = '❌ ' + e.message;
        btn.disabled = false;
        btn.textContent = '▶ СТАРТ ГРИ';
      }}
    }}
  </script>
</body>
</html>""")


@app.get("/game", response_class=HTMLResponse)
async def game_page(session: str = ""):
    if not session:
        return HTMLResponse('<script>window.location="/"</script>')
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="uk">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TIME WARS — Гра</title>
  <style>
    {_CSS_BASE}
    .header {{ position: sticky; top: 0; z-index: 50; background: #0a1628; border-bottom: 1px solid #1e3a5f; padding: 12px 20px; display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }}
    .header-title {{ font-size: .85rem; color: #64748b; letter-spacing: .15em; font-weight: 700; }}
    .tick-wrap {{ display: flex; align-items: center; gap: 10px; flex: 1; }}
    .tick-label {{ font-size: 1.4rem; font-weight: 800; color: #38bdf8; font-variant-numeric: tabular-nums; min-width: 110px; }}
    .progress-outer {{ flex: 1; height: 10px; background: #1e293b; border-radius: 5px; overflow: hidden; min-width: 80px; }}
    .progress-inner {{ height: 100%; background: linear-gradient(90deg, #0ea5e9, #38bdf8); border-radius: 5px; transition: width .5s; width: 0%; }}
    .badge-over {{ background: #14532d; color: #4ade80; padding: 4px 12px; border-radius: 6px; font-size: .85rem; font-weight: 700; display: none; }}
    .btn-menu {{ padding: 6px 14px; background: #1e293b; border-radius: 8px; font-size: .8rem; font-weight: 600; color: #94a3b8; cursor: pointer; border: 1px solid #334155; }}
    .btn-menu:hover {{ background: #273549; color: #e2e8f0; }}
    .btn-human {{ padding: 10px 18px; border-radius: 8px; font-size: .88rem; font-weight: 700; cursor: pointer; border: none; background: #1e3a5f; color: #7dd3fc; transition: background .2s; }}
    .btn-human:hover {{ background: #1e4a7a; color: #e0f2fe; }}
    .btn-human.btn-pass {{ background: #1e293b; color: #64748b; }}
    .btn-human.btn-pass:hover {{ background: #273549; color: #94a3b8; }}
    .btn-human.selected {{ background: #16a34a; color: #fff; box-shadow: 0 0 0 2px #22c55e; }}
    .target-btn {{ padding: 6px 12px; border-radius: 6px; font-size: .78rem; background: #0f1f35; border: 1px solid #334155; color: #94a3b8; cursor: pointer; }}
    .target-btn.selected {{ border-color: #22c55e; color: #4ade80; background: #0a2a1a; }}
    .main {{ max-width: 1100px; margin: 0 auto; padding: 20px; }}
    .players-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; margin-bottom: 16px; }}
    .player-card {{ background: #0f1f35; border: 1px solid #1e3a5f; border-radius: 10px; padding: 14px 16px; transition: all .3s; }}
    .player-card.winner {{ border-color: #22c55e; box-shadow: 0 0 0 2px rgba(34,197,94,.3), 0 0 20px rgba(34,197,94,.15); background: #0a2a1a; }}
    .player-card.eliminated {{ opacity: .5; border-color: #334155; background: #0a0f1a; }}
    .player-card.active-event {{ border-color: #38bdf8; box-shadow: 0 0 0 2px rgba(56,189,248,.3); }}
    .p-name {{ font-weight: 700; color: #f1f5f9; font-size: .95rem; }}
    .p-role {{ font-size: .75rem; color: #f59e0b; margin-top: 3px; }}
    .p-time {{ font-size: 1.5rem; font-weight: 800; color: #38bdf8; margin-top: 8px; font-variant-numeric: tabular-nums; transition: color .3s; }}
    .p-time.zero {{ color: #475569; }}
    .p-time.high {{ color: #4ade80; }}
    .p-time.low {{ color: #ef4444; }}
    .p-status {{ font-size: .7rem; color: #64748b; margin-top: 3px; }}
    .p-mana {{ font-size: .7rem; color: #a78bfa; margin-top: 2px; }}
    .event-log {{ background: #080f1c; border: 1px solid #1e3a5f; border-radius: 10px; padding: 14px; max-height: 260px; overflow-y: auto; font-size: .85rem; }}
    .event-log-title {{ font-size: .75rem; color: #64748b; letter-spacing: .1em; text-transform: uppercase; margin-bottom: 10px; }}
    .event-item {{ padding: 6px 10px; border-radius: 6px; margin-bottom: 5px; line-height: 1.4; }}
    .event-item.coop {{ background: rgba(34,197,94,.1); color: #86efac; border-left: 3px solid #22c55e; }}
    .event-item.steal {{ background: rgba(239,68,68,.1); color: #fca5a5; border-left: 3px solid #ef4444; }}
    .event-item.storm {{ background: rgba(59,130,246,.1); color: #93c5fd; border-left: 3px solid #3b82f6; }}
    .event-item.crisis {{ background: rgba(245,158,11,.1); color: #fcd34d; border-left: 3px solid #f59e0b; }}
    .event-item.round {{ background: rgba(100,116,139,.07); color: #94a3b8; border-left: 3px solid #475569; }}
    .event-item.code {{ background: rgba(167,139,250,.1); color: #c4b5fd; border-left: 3px solid #a78bfa; }}
    .event-item.info {{ background: rgba(56,189,248,.07); color: #7dd3fc; border-left: 3px solid #38bdf8; }}
    .loading-wrap {{ display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 60px 20px; gap: 16px; }}
    .spinner {{ width: 40px; height: 40px; border: 3px solid #1e3a5f; border-top-color: #38bdf8; border-radius: 50%; animation: spin .8s linear infinite; }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    /* Modal */
    .modal-overlay {{ position: fixed; inset: 0; background: rgba(0,0,0,.8); z-index: 200; display: none; align-items: center; justify-content: center; padding: 20px; backdrop-filter: blur(4px); }}
    .modal-overlay.visible {{ display: flex; }}
    .modal {{ background: #0a1628; border: 1px solid #22c55e; border-radius: 16px; padding: 40px 36px; max-width: 500px; width: 100%; text-align: center; box-shadow: 0 0 60px rgba(34,197,94,.2); animation: popIn .3s ease; }}
    @keyframes popIn {{ from {{ transform: scale(.85); opacity: 0; }} to {{ transform: scale(1); opacity: 1; }} }}
    .modal-crown {{ font-size: 3rem; margin-bottom: 12px; }}
    .modal-title {{ font-size: .75rem; color: #64748b; letter-spacing: .15em; text-transform: uppercase; margin-bottom: 8px; }}
    .modal-winner {{ font-size: 2rem; font-weight: 900; color: #4ade80; margin-bottom: 24px; }}
    .modal-standings {{ width: 100%; border-collapse: collapse; margin-bottom: 28px; font-size: .9rem; }}
    .modal-standings td {{ padding: 7px 12px; border-bottom: 1px solid #1e293b; text-align: right; }}
    .modal-standings td:first-child {{ text-align: left; color: #94a3b8; }}
    .modal-standings tr.top td {{ color: #fbbf24; font-weight: 700; }}
    .modal-actions {{ display: flex; flex-direction: column; gap: 10px; }}
    .btn-modal-main {{ background: linear-gradient(135deg, #16a34a, #22c55e); color: #fff; padding: 14px 24px; border-radius: 10px; font-size: .95rem; font-weight: 700; cursor: pointer; border: none; }}
    .btn-modal-main:hover {{ filter: brightness(1.1); }}
    .btn-modal-sec {{ background: #1e293b; color: #94a3b8; padding: 12px 24px; border-radius: 10px; font-size: .9rem; font-weight: 600; cursor: pointer; border: 1px solid #334155; }}
    .btn-modal-sec:hover {{ background: #273549; color: #e2e8f0; }}
  </style>
</head>
<body>
    <header class="header">
    <span class="header-title">TIME WARS</span>
    <div class="tick-wrap">
      <span class="tick-label" id="tick-label">Раунд 0</span>
      <div class="progress-outer"><div class="progress-inner" id="progress-bar"></div></div>
      <span class="badge-over" id="badge-over">Гра завершена</span>
    </div>
    <span id="drain-badge" style="background:#1e0a0a;color:#f87171;border:1px solid #7f1d1d;padding:4px 12px;border-radius:6px;font-size:.8rem;font-weight:700;display:none;">⚡ Дрейн: 1с/тік</span>
    <button class="btn-menu" onclick="window.location='/'">← Меню</button>
  </header>

  <main class="main">
    <div id="loading-wrap" class="loading-wrap">
      <div class="spinner"></div>
      <p style="color:#64748b;font-size:.9rem;">Запускаю гру…</p>
    </div>
    <div id="game-wrap" style="display:none;">
      <div class="players-grid" id="players-grid"></div>
      <!-- Human action panel (only shown when humanSlot=true and it's player's turn) -->
      <div id="human-panel" style="display:none;background:#0a2a1a;border:1px solid #22c55e;border-radius:10px;padding:16px;margin-bottom:14px;">
        <div style="color:#4ade80;font-weight:700;font-size:.9rem;margin-bottom:10px;">⚡ ТВІЙ ХІД — Раунд <span id="human-round">?</span></div>
        <div id="human-targets" style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;"></div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <button id="btn-coop" class="btn-human" onclick="humanAct('cooperate')">🤝 Кооперуватись</button>
          <button id="btn-steal" class="btn-human" onclick="humanAct('steal')">🎭 Вкрасти</button>
          <button id="btn-pass" class="btn-human btn-pass" onclick="humanAct('pass')">⏭ Пас</button>
        </div>
        <div id="human-status" style="font-size:.75rem;color:#64748b;margin-top:8px;"></div>
      </div>
      <div class="event-log">
        <div class="event-log-title">Перебіг гри</div>
        <div id="event-list"></div>
      </div>
    </div>
  </main>

  <!-- Game Over Modal -->
  <div class="modal-overlay" id="modal">
    <div class="modal">
      <div class="modal-crown">🏆</div>
      <div class="modal-title">Гра завершена</div>
      <div class="modal-winner" id="modal-winner">—</div>
      <table class="modal-standings" id="modal-standings"></table>
      <div class="modal-actions">
        <button class="btn-modal-main" id="btn-report" onclick="openReport()">Переглянути повний звіт</button>
        <button class="btn-modal-sec" onclick="window.location='/results'">Всі результати</button>
        <button class="btn-modal-sec" onclick="window.location='/'">Головне меню</button>
      </div>
    </div>
  </div>

  <script>
  (function() {{
    const SESSION_ID = {json.dumps(session)};
    const IS_HUMAN = {json.dumps(bool(_sessions_human.get(session, False)))};
    let players = {{}};   // id → {{name, role, timeSec, status, mana, eliminationPlace, killedBy}}
    let tickTotal = 1000;   // battle royale — no fixed cap shown
    let baseSec = 300;
    let drainDoubleEvery = 5;
    let reportPath = null;
    let humanAgentId = null;   // set when role_assignment event arrives for human slot
    let currentRound = 0;
    let selectedTarget = null;
    let eliminationOrder = 0;          // increments each time a player is eliminated
    let lastStolenBy = {{}};            // agent_id → {{name, id}} — who last successfully stole from them

    function getEl(id) {{ return document.getElementById(id); }}

    function renderPlayers() {{
      const sorted = Object.values(players).sort((a,b) => {{
        if (a.winnerId) return -1;
        if (b.winnerId) return 1;
        if (a.status === 'eliminated' && b.status !== 'eliminated') return 1;
        if (b.status === 'eliminated' && a.status !== 'eliminated') return -1;
        if (a.status === 'eliminated' && b.status === 'eliminated')
          return (b.eliminationPlace || 0) - (a.eliminationPlace || 0);
        return b.timeSec - a.timeSec;
      }});
      getEl('players-grid').innerHTML = sorted.map(p => {{
        const cls = p.winnerId ? 'winner' : p.status === 'eliminated' ? 'eliminated' : p.activeEvent ? 'active-event' : '';
        const timeClass = p.timeSec <= 0 ? 'zero' : p.timeSec > baseSec * 0.6 ? 'high' : p.timeSec < baseSec * 0.2 ? 'low' : '';
        let statusText;
        if (p.winnerId) {{
          statusText = '🏆 Переможець';
        }} else if (p.status === 'eliminated') {{
          const place = p.eliminationPlace ? `${{p.eliminationPlace}}-й вибув` : 'Вибув';
          statusText = p.killedBy ? `💀 ${{place}} · ← ${{p.killedBy}}` : `💀 ${{place}}`;
        }} else {{
          statusText = 'Активний';
        }}
        return `<div class="player-card ${{cls}}">
          <div class="p-name">${{p.name}}</div>
          <div class="p-role">${{p.role}}</div>
          <div class="p-time ${{timeClass}}">${{Math.max(0, p.timeSec)}}с</div>
          <div class="p-status">${{statusText}}</div>
          <div class="p-mana">Мана: ${{p.mana !== undefined ? Math.round(p.mana) : '—'}}</div>
        </div>`;
      }}).join('');
    }}

    function addEvent(text, type) {{
      const div = document.createElement('div');
      div.className = 'event-item ' + (type || '');
      div.textContent = text;
      const list = getEl('event-list');
      list.insertBefore(div, list.firstChild);
    }}

    function handleEvent(ev) {{
      const et = ev.event_type;

      if (et === 'game_start') {{
        baseSec = ev.base_seconds_per_player || 300;
        drainDoubleEvery = ev.drain_double_every || 5;
        getEl('loading-wrap').style.display = 'none';
        getEl('game-wrap').style.display = 'block';
        getEl('drain-badge').style.display = 'inline-block';
        addEvent('⚔ Баттл Роял! Дрейн подвоюється кожні ' + drainDoubleEvery + ' тіків', 'info');
        return;
      }}

      if (et === 'role_assignment') {{
        if (!players[ev.agent_id]) players[ev.agent_id] = {{}};
        players[ev.agent_id] = {{
          id: ev.agent_id,
          name: ev.agent_id_name || ev.agent_id,
          role: ev.role_name || ev.role_id || '—',
          timeSec: baseSec,
          status: 'active',
          mana: 20,
        }};
        // Last role_assignment is the human slot (if human game)
        if (IS_HUMAN) humanAgentId = ev.agent_id;
        renderPlayers();
        return;
      }}

      if (et === 'round_start') {{
        const tick = ev.tick || 0;
        const drain = ev.drain_sec || 1;
        const active = Object.values(players).filter(p => p.status === 'active').length;
        currentRound = ev.round_num;
        getEl('tick-label').textContent = `Раунд ${{ev.round_num}} · Тік ${{tick}} · Живі: ${{active}}`;
        getEl('drain-badge').textContent = `⚡ Дрейн: ${{drain}}с/тік`;
        const badge = getEl('drain-badge');
        if (drain > 1) {{
          badge.style.borderColor = '#dc2626';
          badge.style.color = '#fca5a5';
          badge.style.boxShadow = `0 0 10px rgba(220,38,38,${{Math.min(0.8, drain/64)}})`;
        }}
        addEvent(`— Раунд ${{ev.round_num}} (тік ${{tick}}) · ⚡ ${{drain}}с/тік · Живі: ${{active}} —`, 'round');
        Object.values(players).forEach(p => p.activeEvent = false);

        // Sync authoritative times/mana from round_start snapshot (after drain, before actions)
        if (ev.players) {{
          ev.players.forEach(p => {{
            if (players[p.agent_id]) {{
              players[p.agent_id].timeSec = p.time_remaining_sec;
              players[p.agent_id].mana = p.mana;
              if (p.status === 'eliminated') players[p.agent_id].status = 'eliminated';
            }}
          }});
          renderPlayers();
        }}

        // Show human action panel if this is a human-slot game
        if (IS_HUMAN && humanAgentId && players[humanAgentId] && players[humanAgentId].status === 'active') {{
          showHumanPanel(tick);
        }}
        return;
      }}

      if (et === 'cooperate') {{
        const a = ev.actor_id_name || ev.actor_id, b = ev.target_id_name || ev.target_id;
        const delta = ev.time_delta_seconds || 0;
        addEvent(`🤝 ${{a}} + ${{b}} кооперують (+${{delta}}с кожному)`, 'coop');
        if (players[ev.actor_id]) {{
          players[ev.actor_id].timeSec += delta;
          if (ev.mana_actor_after !== undefined) players[ev.actor_id].mana = ev.mana_actor_after;
          players[ev.actor_id].activeEvent = true;
        }}
        if (players[ev.target_id]) {{
          players[ev.target_id].timeSec += delta;
          if (ev.mana_target_after !== undefined) players[ev.target_id].mana = ev.mana_target_after;
          players[ev.target_id].activeEvent = true;
        }}
        renderPlayers();
        return;
      }}

      if (et === 'steal') {{
        const delta = ev.time_delta_seconds || 0;
        if (ev.target_effect) {{
          // Target-side event: target loses time
          if (players[ev.target_id]) {{
            players[ev.target_id].timeSec = Math.max(0, players[ev.target_id].timeSec + delta);
            players[ev.target_id].activeEvent = true;
          }}
          renderPlayers();
          return;
        }}
        // Actor-side event
        const a = ev.actor_id_name || ev.actor_id, b = ev.target_id_name || ev.target_id;
        const outcome = ev.outcome || '';
        if (outcome === 'success' || outcome === 'partial') {{
          addEvent(`🎭 ${{a}} вкрав у ${{b}} (+${{delta}}с)`, 'steal');
          if (ev.target_id) lastStolenBy[ev.target_id] = {{ name: a, id: ev.actor_id }};
        }} else {{
          addEvent(`🎭 ${{a}} намагався вкрасти у ${{b}} — провал (${{delta}}с)`, 'steal');
        }}
        if (players[ev.actor_id]) {{
          players[ev.actor_id].timeSec = Math.max(0, players[ev.actor_id].timeSec + delta);
          if (ev.mana_actor_after !== undefined) players[ev.actor_id].mana = ev.mana_actor_after;
          players[ev.actor_id].activeEvent = true;
        }}
        renderPlayers();
        return;
      }}

      if (et === 'storm') {{
        const delta = Math.abs(ev.delta_sec || ev.time_delta_seconds || 15);
        addEvent(`⛈ ШТОРМ — усі втрачають ${{delta}}с`, 'storm');
        Object.values(players).forEach(p => {{ p.timeSec = Math.max(0, p.timeSec - delta); }});
        renderPlayers();
        return;
      }}

      if (et === 'crisis') {{
        const penalty = Math.abs(ev.penalty_sec || ev.time_delta_seconds || 15);
        addEvent(`⚠ КРИЗА — слабкі гравці −${{penalty}}с`, 'crisis');
        return;
      }}

      if (et === 'code_use') {{
        const a = ev.actor_id_name || ev.actor_id;
        const selfDelta = ev.time_delta_seconds || 0;
        const targetDelta = ev.target_delta_seconds || 0;
        addEvent(`💡 ${{a}} використав код «${{ev.code_id || '?'}}» (+${{selfDelta}}с)`, 'code');
        if (players[ev.actor_id]) {{
          players[ev.actor_id].timeSec = Math.max(0, players[ev.actor_id].timeSec + selfDelta);
          if (ev.mana_actor_after !== undefined) players[ev.actor_id].mana = ev.mana_actor_after;
          players[ev.actor_id].activeEvent = true;
        }}
        if (ev.target_id && targetDelta !== 0 && players[ev.target_id]) {{
          players[ev.target_id].timeSec = Math.max(0, players[ev.target_id].timeSec + targetDelta);
          players[ev.target_id].activeEvent = true;
        }}
        renderPlayers();
        return;
      }}

      if (et === 'elimination') {{
        eliminationOrder++;
        const name = ev.target_id_name || ev.target_id;
        const killer = lastStolenBy[ev.target_id];
        if (players[ev.target_id]) {{
          players[ev.target_id].status = 'eliminated';
          players[ev.target_id].timeSec = 0;
          players[ev.target_id].eliminationPlace = eliminationOrder;
          players[ev.target_id].killedBy = killer ? killer.name : null;
        }}
        const killerStr = killer ? ` ← ${{killer.name}}` : '';
        addEvent(`💀 ${{name}} вибув ${{eliminationOrder}}-м${{killerStr}}`, 'steal');
        renderPlayers();
        return;
      }}

      if (et === 'comm_message') {{
        const sender = ev.sender_id_name || ev.sender_id || '?';
        const ch = ev.channel || 'public';
        const icon = ch === 'public' ? '💬' : '📩';
        const channelLabel = ch === 'public' ? '' : ' (приватне)';
        addEvent(`${{icon}} ${{sender}}${{channelLabel}}: «${{ev.text || ''}}»`, 'coop');
        return;
      }}

      if (et === 'game_over') {{
        const tick = ev.tick || tickTotal;
        getEl('tick-label').textContent = `Тік ${{tick}} / ${{tickTotal}}`;
        getEl('progress-bar').style.width = '100%';
        getEl('badge-over').style.display = 'block';

        const winnerId = ev.winner_id;
        const winnerName = ev.winner_id_name || winnerId || '—';
        if (players[winnerId]) players[winnerId].winnerId = true;
        renderPlayers();

        // Update all final times
        if (ev.final_times_named) {{
          Object.entries(ev.final_times_named).forEach(([name, sec]) => {{
            const p = Object.values(players).find(p => p.name === name);
            if (p) p.timeSec = sec;
          }});
          renderPlayers();
        }}

        // Show modal
        getEl('modal-winner').textContent = winnerName + ' переміг!';
        // Sort: winner first, then by reverse elimination order (last eliminated = 2nd place)
        const standings = Object.values(players).sort((a, b) => {{
          if (a.winnerId) return -1;
          if (b.winnerId) return 1;
          if (a.eliminationPlace && b.eliminationPlace) return b.eliminationPlace - a.eliminationPlace;
          if (a.eliminationPlace) return 1;
          if (b.eliminationPlace) return -1;
          return b.timeSec - a.timeSec;
        }});
        getEl('modal-standings').innerHTML = standings.map((p, i) => {{
          const placeIcon = p.winnerId ? '🏆' : `💀${{p.eliminationPlace || '?'}}`;
          const killedByStr = p.killedBy ? `<span style="color:#94a3b8;font-size:.8em"> ← ${{p.killedBy}}</span>` : '';
          return `<tr class="${{i===0 ? 'top' : ''}}">
            <td>${{placeIcon}} ${{p.name}} (${{p.role}})${{killedByStr}}</td>
            <td>${{Math.max(0, p.timeSec)}}с</td>
          </tr>`;
        }}).join('');
        setTimeout(() => getEl('modal').classList.add('visible'), 600);
        return;
      }}
    }}

    function openReport() {{
      if (reportPath) window.open(reportPath, '_blank');
      else window.location = '/results';
    }}

    // Human player panel
    function showHumanPanel(tick) {{
      selectedTarget = null;
      getEl('human-round').textContent = currentRound;
      getEl('human-status').textContent = '';
      // Render target buttons
      const others = Object.values(players).filter(p => p.status === 'active' && p.id !== humanAgentId);
      getEl('human-targets').innerHTML = others.map(p =>
        `<button class="target-btn" id="tgt-${{p.id}}" onclick="selectTarget('${{p.id}}')">${{p.name}}</button>`
      ).join('');
      // Store current tick for submission
      getEl('human-panel').dataset.tick = tick;
      getEl('human-panel').style.display = 'block';
    }}

    function selectTarget(id) {{
      selectedTarget = id;
      document.querySelectorAll('.target-btn').forEach(b => b.classList.remove('selected'));
      const btn = document.getElementById('tgt-' + id);
      if (btn) btn.classList.add('selected');
    }}

    function humanAct(action) {{
      const tick = parseInt(getEl('human-panel').dataset.tick || '0');
      const target = selectedTarget || '';
      if ((action === 'cooperate' || action === 'steal') && !target) {{
        getEl('human-status').textContent = '⚠ Оберіть ціль';
        return;
      }}
      getEl('human-panel').style.display = 'none';
      fetch('/api/human-action/' + SESSION_ID, {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{tick, action, target_id: target}}),
      }}).catch(console.error);
      addEvent(`👤 Ти: ${{action}} ${{target ? '→ ' + (players[target]?.name || target) : ''}}`, 'info');
    }}

    // Connect to SSE
    const evtSource = new EventSource('/api/game-events/' + SESSION_ID);
    evtSource.onmessage = function(e) {{
      try {{
        const ev = JSON.parse(e.data);
        if (ev.event_type === '__progress__') {{
          const st = getEl('status');
          if (st) st.textContent = 'Раунд ' + (ev.round || 0) + ' (тік ' + (ev.tick || 0) + ') · активних: ' + (ev.active || 0);
          return;
        }}
        if (ev.event_type === '__stream_end__') {{
          reportPath = ev.reportPath;
          const reportBtn = getEl('btn-report');
          if (reportBtn && reportPath) {{
            reportBtn.textContent = 'Переглянути повний звіт →';
            reportBtn.onclick = () => window.open(reportPath, '_blank');
          }}
          evtSource.close();
          return;
        }}
        handleEvent(ev);
      }} catch(err) {{ console.error(err); }}
    }};
    evtSource.onerror = function() {{
      evtSource.close();
    }};
  }})();
  </script>
</body>
</html>""")


@app.get("/results", response_class=HTMLResponse)
async def results_page():
    sessions = _get_sessions()

    # Collect ALL unique agent names across ALL sessions (fix: was only from first session)
    agent_totals: dict[str, int] = {}
    agent_appearances: dict[str, int] = {}
    agent_wins: dict[str, int] = {}
    for s in sessions:
        for name, val in s["finalTimes"].items():
            agent_totals[name] = agent_totals.get(name, 0) + val
            agent_appearances[name] = agent_appearances.get(name, 0) + 1
        if s["winner"]:
            agent_wins[s["winner"]] = agent_wins.get(s["winner"], 0) + 1
    agent_names = sorted(agent_appearances.keys(), key=lambda n: -agent_appearances[n])
    agent_totals_compat = agent_totals  # alias for template

    def _row(s: dict) -> str:
        cells = "".join(
            f'<td class="sec{"" if s["winner"] != n else " win"}">'
            f'{"—" if n not in s["finalTimes"] else str(s["finalTimes"][n]) + "с"}'
            f'</td>'
            for n in agent_names
        )
        survivor_info = f'{s.get("survivorCount", 0)}/{s.get("totalPlayers", 0)}'
        report_btn = (
            f'<a class="btn-sm btn-green" href="{s["reportPath"]}" target="_blank">Відкрити</a>'
            if s.get("reportPath") else '<span style="color:#475569;font-size:.75rem">—</span>'
        )
        return (
            f'<tr data-winner="{s["winner"]}">'
            f'<td class="ts">{s["playedAt"]}</td>'
            f'<td class="num">{s["tick"]}</td>'
            f'<td class="win-cell">{s["winner"]}</td>'
            f'<td class="surv">{survivor_info}</td>'
            f'{cells}'
            f'<td>{report_btn}</td>'
            f'</tr>'
        )

    total_row = "".join(f'<td class="sec">{agent_totals.get(n, 0)}с</td>' for n in agent_names)
    best_row = "".join(
        f'<td class="sec">{max((s["finalTimes"].get(n, 0) for s in sessions), default=0)}с</td>'
        for n in agent_names
    )
    wins_row = "".join(
        f'<td class="sec" style="color:#a78bfa">{agent_wins.get(n, 0)}</td>'
        for n in agent_names
    )
    header_agents = "".join(f'<th class="right">{n}</th>' for n in agent_names)
    rows_html = "".join(_row(s) for s in sessions) if sessions else (
        '<tr><td colspan="20" style="text-align:center;padding:48px;color:#475569;">'
        'Немає ігор. Натисни "Нова гра" або <code>python run_time_wars.py</code></td></tr>'
    )

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="uk">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TIME WARS — Результати</title>
  <style>
    {_CSS_BASE}
    body {{ padding: 32px 20px; }}
    .page-header {{ display: flex; align-items: center; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }}
    h1 {{ font-size: 1.5rem; font-weight: 900; color: #4ade80; letter-spacing: .1em; }}
    .sub {{ color: #64748b; font-size: .9rem; margin-left: 4px; }}
    .actions {{ display: flex; gap: 10px; margin-left: auto; flex-wrap: wrap; }}
    .filter-bar {{ display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; align-items: center; }}
    .filter-bar input, .filter-bar select {{ background: #0a1628; border: 1px solid #1e3a5f; color: #e2e8f0; padding: 6px 10px; border-radius: 6px; font-size: .85rem; }}
    .filter-bar label {{ color: #64748b; font-size: .8rem; }}
    .stats-bar {{ display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }}
    .stat-chip {{ background: #0a1628; border: 1px solid #1e3a5f; border-radius: 8px; padding: 8px 16px; font-size: .78rem; color: #94a3b8; }}
    .stat-chip strong {{ color: #4ade80; font-size: 1rem; display: block; }}
    .table-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; background: #080f1c; border: 1px solid #1e3a5f; border-radius: 10px; overflow: hidden; font-size: .85rem; min-width: 600px; }}
    thead {{ background: #0a1628; }}
    th {{ padding: 10px 10px; text-align: left; font-size: .68rem; letter-spacing: .08em; color: #4ade80; border-bottom: 1px solid #1e3a5f; text-transform: uppercase; font-weight: 700; white-space: nowrap; }}
    th.right {{ text-align: right; }}
    td {{ padding: 8px 10px; border-bottom: 1px solid #0f1f35; white-space: nowrap; }}
    td.sec {{ text-align: right; color: #475569; font-size: .8rem; }}
    td.sec.win {{ color: #fbbf24; font-weight: 700; }}
    td.win-cell {{ color: #fbbf24; font-weight: 700; }}
    td.ts {{ color: #38bdf8; font-size: .75rem; }}
    td.num {{ color: #475569; font-size: .8rem; }}
    td.surv {{ color: #94a3b8; font-size: .8rem; text-align: center; }}
    tr:hover {{ background: rgba(74,222,128,.04); }}
    tr.row-hidden {{ display: none; }}
    .total-row td {{ background: rgba(74,222,128,.07); color: #4ade80; font-weight: 700; font-size: .78rem; }}
    .best-row td {{ background: #080f1c; color: #38bdf8; font-size: .78rem; }}
    .wins-row td {{ background: #080f1c; color: #a78bfa; font-size: .78rem; }}
    .btn-green {{ background: #16a34a; color: #fff; padding: 5px 12px; border-radius: 6px; font-size: .78rem; font-weight: 700; border: none; cursor: pointer; text-decoration: none; display: inline-block; }}
    .btn-green:hover {{ background: #15803d; }}
    code {{ background: #1e293b; padding: 2px 6px; border-radius: 4px; color: #38bdf8; font-size: .85em; }}
    #run-status {{ font-size: .85rem; color: #4ade80; min-height: 20px; margin-bottom: 8px; }}
    .page-btns {{ display: flex; gap: 6px; margin-top: 14px; align-items: center; flex-wrap: wrap; }}
    .page-btns button {{ background: #1e293b; border: 1px solid #334155; color: #94a3b8; padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: .8rem; }}
    .page-btns button:hover {{ background: #273549; }}
    .page-btns button.pg-active {{ background: #16a34a; color: #fff; border-color: #16a34a; }}
    #page-info {{ color: #64748b; font-size: .8rem; margin-top: 6px; }}
  </style>
</head>
<body>
  <div class="page-header">
    <div>
      <h1>TIME WARS <span class="sub">— {len(sessions)} сесій</span></h1>
    </div>
    <div class="actions">
      <button class="btn btn-green" onclick="runGame()">▶ Нова гра</button>
      <a href="/" class="btn btn-slate">← Меню</a>
    </div>
  </div>
  <div id="run-status"></div>

  <div class="stats-bar">
    <div class="stat-chip"><strong>{len(sessions)}</strong>ігор зіграно</div>
    <div class="stat-chip"><strong>{max(agent_wins.values(), default=0)}</strong>макс перемог</div>
    <div class="stat-chip"><strong>{len(agent_names)}</strong>унікальних гравців</div>
    <div class="stat-chip"><strong>{max((s["tick"] for s in sessions), default=0)}</strong>макс тіків</div>
  </div>

  <div class="filter-bar">
    <label>Пошук:</label>
    <input type="text" id="search-input" placeholder="ім'я переможця..." oninput="applyFilter()">
    <label style="margin-left:8px">Рядків:</label>
    <select id="page-size" onchange="applyFilter()">
      <option value="20">20</option>
      <option value="50">50</option>
      <option value="100">100</option>
      <option value="9999">Всі</option>
    </select>
  </div>

  <div class="table-wrap">
  <table id="results-table">
    <thead>
      <tr>
        <th>Дата</th><th>Тіків</th><th>Переможець</th><th style="text-align:center">Вижили</th>
        {header_agents}
        <th>Звіт</th>
      </tr>
    </thead>
    <tbody id="results-body">
      {rows_html}
    </tbody>
    <tfoot>
      <tr class="wins-row">
        <td colspan="4">ПЕРЕМОГИ</td>{wins_row}<td></td>
      </tr>
      <tr class="best-row">
        <td colspan="4">РЕКОРД (макс)</td>{best_row}<td></td>
      </tr>
      <tr class="total-row">
        <td colspan="4">СУМА ЧАСУ</td>{total_row}<td></td>
      </tr>
    </tfoot>
  </table>
  </div>
  <div class="page-btns" id="page-btns"></div>
  <div id="page-info"></div>

  <script>
    var allRows = Array.from(document.querySelectorAll('#results-body tr'));
    var filtered = allRows.slice();
    var curPage = 1;

    function applyFilter() {{
      var q = document.getElementById('search-input').value.toLowerCase();
      filtered = q
        ? allRows.filter(function(r) {{ return r.textContent.toLowerCase().indexOf(q) >= 0; }})
        : allRows.slice();
      showPage(1);
    }}

    function showPage(page) {{
      curPage = page;
      var size = parseInt(document.getElementById('page-size').value);
      var total = Math.ceil(filtered.length / size) || 1;
      allRows.forEach(function(r) {{ r.classList.add('row-hidden'); }});
      filtered.slice((page-1)*size, page*size).forEach(function(r) {{ r.classList.remove('row-hidden'); }});
      var btns = document.getElementById('page-btns');
      while (btns.firstChild) {{ btns.removeChild(btns.firstChild); }}
      if (total > 1) {{
        for (var i = 1; i <= total; i++) {{
          var b = document.createElement('button');
          b.textContent = String(i);
          if (i === page) b.classList.add('pg-active');
          (function(p) {{ b.addEventListener('click', function() {{ showPage(p); }}); }})(i);
          btns.appendChild(b);
        }}
      }}
      var info = document.getElementById('page-info');
      info.textContent = filtered.length < allRows.length
        ? ('Показано ' + filtered.length + ' з ' + allRows.length + ' сесій')
        : (allRows.length + ' сесій');
    }}

    async function runGame() {{
      document.getElementById('run-status').textContent = '⏳ Запускаю нову гру...';
      try {{
        var r = await fetch('/api/start-game', {{ method: 'POST' }});
        var d = await r.json();
        if (d.sessionId) window.location.href = '/game?session=' + d.sessionId;
      }} catch(e) {{
        document.getElementById('run-status').textContent = '❌ ' + e.message;
      }}
    }}

    showPage(1);
  </script>
</body>
</html>""")


# ── Static logs ────────────────────────────────────────────────────────────

app.mount("/logs", StaticFiles(directory=str(LOGS_ROOT)), name="logs")


# ── Entry point ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="TIME WARS standalone server")
    parser.add_argument("--port", type=int, default=5174)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    args = parser.parse_args()
    print(f"\n  TIME WARS  ->  http://localhost:{args.port}")
    print(f"  Menu       ->  http://localhost:{args.port}/")
    print(f"  Results    ->  http://localhost:{args.port}/results\n")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
