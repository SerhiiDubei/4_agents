"""
TIME WARS logs: write event_log to JSONL file; optional TIMER-format export for Supabase.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List, Optional

from game_modes.time_wars.state import Session


def write_session_log(
    session: Session,
    log_dir: Path,
    session_id: Optional[str] = None,
    suffix: Optional[str] = None,
) -> Path:
    """
    Write session.event_log to logs/time_wars_<session_id>_<timestamp>.jsonl.
    Returns path to created file.
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    sid = session_id or session.session_id
    ts = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
    name = f"time_wars_{sid}_{ts}"
    if suffix:
        name += f"_{suffix}"
    path = log_dir / f"{name}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for ev in session.event_log:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return path


def event_to_timer_format(ev: dict, room_id: str) -> dict:
    """
    Convert one TIME WARS event to TIMER-style record for Supabase events table.
    room_id = session_id = TIMER room.
    """
    out = {
        "room_id": room_id,
        "event_type": ev.get("event_type", ""),
        "actor_id": ev.get("actor_id"),
        "target_id": ev.get("target_id"),
        "time_delta_seconds": ev.get("time_delta_seconds"),
        "payload": {k: v for k, v in ev.items() if k not in ("event_type", "actor_id", "target_id", "time_delta_seconds", "tick", "timestamp")},
        "timestamp": ev.get("timestamp"),
    }
    return out


def export_to_timer_events(session: Session, room_id: Optional[str] = None) -> List[dict]:
    """
    Return list of events in TIMER-compatible format (for Supabase import or API).
    """
    rid = room_id or session.session_id
    return [event_to_timer_format(ev, rid) for ev in session.event_log]
