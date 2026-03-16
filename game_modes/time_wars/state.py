"""
TIME WARS state: Session (= room), Player (time, role, inventory), trust.
Role assignment from roles.json (random or config).
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from game_modes.time_wars.constants import DEFAULT_BASE_SECONDS_PER_PLAYER

_ROLES_PATH = Path(__file__).resolve().parent / "roles.json"


@dataclass
class Player:
    """One player in a TIME WARS session. Maps to TIMER player + role + inventory."""
    agent_id: str
    time_remaining_sec: int
    role_id: str
    inventory: List[dict] = field(default_factory=list)  # list of code items: {"code_id": str, "effect_type": str, "seconds": int}
    status: str = "active"  # active | eliminated

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "time_remaining_sec": self.time_remaining_sec,
            "role_id": self.role_id,
            "inventory": list(self.inventory),
            "status": self.status,
        }


@dataclass
class Session:
    """One TIME WARS game session. Conceptually = TIMER room."""
    session_id: str
    game_start_time: float  # epoch sec
    base_seconds_per_player: int
    duration_limit_sec: int
    players: List[Player] = field(default_factory=list)
    trust: Dict[tuple, float] = field(default_factory=dict)  # (actor_id, target_id) -> 0.0..1.0
    event_log: List[dict] = field(default_factory=list)

    def get_player(self, agent_id: str) -> Optional[Player]:
        for p in self.players:
            if p.agent_id == agent_id:
                return p
        return None

    def get_trust(self, actor_id: str, target_id: str) -> float:
        return self.trust.get((actor_id, target_id), 0.5)

    def set_trust(self, actor_id: str, target_id: str, value: float) -> None:
        self.trust[(actor_id, target_id)] = max(0.0, min(1.0, value))

    def active_players(self) -> List[Player]:
        return [p for p in self.players if p.status == "active"]

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "game_start_time": self.game_start_time,
            "base_seconds_per_player": self.base_seconds_per_player,
            "duration_limit_sec": self.duration_limit_sec,
            "players": [p.to_dict() for p in self.players],
            "trust": {f"{a}:{b}": v for (a, b), v in self.trust.items()},
        }


def load_roles(path: Optional[Path] = None) -> dict:
    """Load roles from roles.json. Returns {"roles": [ {...}, ... ]}."""
    p = path or _ROLES_PATH
    if not p.exists():
        return {"roles": []}
    return json.loads(p.read_text(encoding="utf-8"))


def assign_roles(
    agent_ids: List[str],
    roles_config: Optional[dict] = None,
    role_override: Optional[Dict[str, str]] = None,
    shuffle: bool = True,
) -> Dict[str, str]:
    """
    Assign role_id to each agent_id.
    roles_config: from load_roles()["roles"]; if None, loads from file.
    role_override: optional {agent_id: role_id} to force specific roles.
    shuffle: if True, shuffle role order so assignment is random.
    Returns {agent_id: role_id}.
    """
    if roles_config is None:
        data = load_roles()
        roles_list = data.get("roles", [])
    else:
        roles_list = roles_config.get("roles", roles_config) if isinstance(roles_config, dict) else roles_config
    role_ids = [r["id"] for r in roles_list if isinstance(r, dict) and "id" in r]
    if not role_ids:
        return {aid: "role_snake" for aid in agent_ids}
    result = {}
    if role_override:
        result.update(role_override)
    remaining_agents = [a for a in agent_ids if a not in result]
    if shuffle:
        random.shuffle(remaining_agents)
    for i, aid in enumerate(remaining_agents):
        result[aid] = role_ids[i % len(role_ids)]
    return result


def create_session(
    session_id: str,
    agent_ids: List[str],
    base_seconds_per_player: int = DEFAULT_BASE_SECONDS_PER_PLAYER,
    duration_limit_sec: Optional[int] = None,
    role_override: Optional[Dict[str, str]] = None,
    start_time: Optional[float] = None,
) -> Session:
    """Create a new session with players and assigned roles."""
    import time
    if duration_limit_sec is None:
        duration_limit_sec = base_seconds_per_player
    if start_time is None:
        start_time = time.time()
    assignments = assign_roles(agent_ids, role_override=role_override)
    players = [
        Player(
            agent_id=aid,
            time_remaining_sec=base_seconds_per_player,
            role_id=assignments.get(aid, "role_snake"),
            inventory=[],
            status="active",
        )
        for aid in agent_ids
    ]
    session = Session(
        session_id=session_id,
        game_start_time=start_time,
        base_seconds_per_player=base_seconds_per_player,
        duration_limit_sec=duration_limit_sec,
        players=players,
        trust={},
        event_log=[],
    )
    # Initialize trust between all pairs
    for a in agent_ids:
        for b in agent_ids:
            if a != b:
                session.set_trust(a, b, 0.5)
    return session
