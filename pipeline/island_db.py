"""
island_db.py — Island game persistence helpers.

Writes to the same timewars.db SQLite used by Time Wars.
Called from run_simulation_live.py after each game ends.
Also queried by /api/island/leaderboard and /api/island/history.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.database import SessionLocal, engine
from db.models import Base, IslandGame


def init_island_db() -> None:
    """Create island_games table if it doesn't exist yet."""
    Base.metadata.create_all(bind=engine)


# ─── Save ────────────────────────────────────────────────────────────────────

def save_game_result(
    game_id: str,
    agent_ids: List[str],
    agent_names: Dict[str, str],          # agent_id → display name
    final_scores: Dict[str, float],       # agent_id → score
    round_actions: List[Dict],            # list of RoundResult.actions dicts
    rounds: int,
    winner: Optional[str] = None,
    world_prompt: str = "",
) -> None:
    """
    Persist one completed Island game.
    round_actions — list of {agent_id: {target_id: float}} per round.
    Action value: >=0.66 = cooperate, <=0.33 = betray, else neutral.
    """
    # Count coop/betray/neutral per agent across all rounds
    coop:    Dict[str, int] = {a: 0 for a in agent_ids}
    betray:  Dict[str, int] = {a: 0 for a in agent_ids}
    neutral: Dict[str, int] = {a: 0 for a in agent_ids}

    for round_acts in round_actions:
        for agent_id, targets in round_acts.items():
            if agent_id not in agent_ids:
                continue
            for val in targets.values():
                if val >= 0.66:
                    coop[agent_id] += 1
                elif val <= 0.33:
                    betray[agent_id] += 1
                else:
                    neutral[agent_id] += 1

    agents_data = [
        {
            "agent_id":     aid,
            "name":         agent_names.get(aid, aid[-8:]),
            "score":        round(final_scores.get(aid, 0.0), 2),
            "coop_count":   coop[aid],
            "betray_count": betray[aid],
            "neutral_count": neutral[aid],
        }
        for aid in agent_ids
    ]

    winner_name = agent_names.get(winner, winner) if winner else None

    row = IslandGame(
        game_id      = game_id,
        played_at    = datetime.utcnow(),
        rounds       = rounds,
        world_prompt = world_prompt[:500] if world_prompt else "",
        winner_id    = winner,
        winner_name  = winner_name,
        agents_json  = json.dumps(agents_data, ensure_ascii=False),
    )

    db = SessionLocal()
    try:
        db.add(row)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[island_db] save failed: {e}", flush=True)
    finally:
        db.close()


# ─── Query ───────────────────────────────────────────────────────────────────

def get_leaderboard(limit: int = 100) -> List[dict]:
    """
    Aggregate per-agent stats across ALL island games.
    Returns list of dicts sorted by avg_score desc.
    """
    db = SessionLocal()
    try:
        rows = db.query(IslandGame).order_by(IslandGame.played_at.desc()).limit(limit * 10).all()
    finally:
        db.close()

    # Aggregate by agent_id
    agg: Dict[str, dict] = {}
    for row in rows:
        try:
            agents = json.loads(row.agents_json)
        except Exception:
            continue
        for a in agents:
            aid = a["agent_id"]
            if aid not in agg:
                agg[aid] = {
                    "agent_id":     aid,
                    "name":         a["name"],
                    "games":        0,
                    "wins":         0,
                    "total_score":  0.0,
                    "total_coop":   0,
                    "total_betray": 0,
                    "total_neutral": 0,
                    "total_actions": 0,
                }
            agg[aid]["games"]        += 1
            agg[aid]["wins"]         += 1 if row.winner_id == aid else 0
            agg[aid]["total_score"]  += a["score"]
            agg[aid]["total_coop"]   += a["coop_count"]
            agg[aid]["total_betray"] += a["betray_count"]
            agg[aid]["total_neutral"] += a["neutral_count"]
            total = a["coop_count"] + a["betray_count"] + a["neutral_count"]
            agg[aid]["total_actions"] += total

    result = []
    for a in agg.values():
        g = a["games"]
        acts = a["total_actions"] or 1
        result.append({
            "agent_id":   a["agent_id"],
            "name":       a["name"],
            "games":      g,
            "wins":       a["wins"],
            "win_rate":   round(a["wins"] / g * 100, 1),
            "avg_score":  round(a["total_score"] / g, 2),
            "coop_pct":   round(a["total_coop"] / acts * 100, 1),
            "betray_pct": round(a["total_betray"] / acts * 100, 1),
        })

    result.sort(key=lambda x: x["avg_score"], reverse=True)
    return result[:limit]


def get_recent_games(limit: int = 20) -> List[dict]:
    """Last N games with summary per game."""
    db = SessionLocal()
    try:
        rows = db.query(IslandGame).order_by(IslandGame.played_at.desc()).limit(limit).all()
    finally:
        db.close()

    out = []
    for row in rows:
        try:
            agents = json.loads(row.agents_json)
        except Exception:
            agents = []
        out.append({
            "game_id":     row.game_id,
            "played_at":   row.played_at.strftime("%Y-%m-%d %H:%M") if row.played_at else "",
            "rounds":      row.rounds,
            "winner_name": row.winner_name,
            "agents":      agents,
        })
    return out
