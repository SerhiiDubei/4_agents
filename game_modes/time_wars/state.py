"""
TIME WARS state: Session (= room), Player (time, role, inventory), trust.
Role assignment from roles.json (random or config).
Trust initialization from cross-game MEMORY.json trust_history or CORE.json similarity.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from game_modes.time_wars.constants import DEFAULT_BASE_SECONDS_PER_PLAYER

_ROLES_PATH = Path(__file__).resolve().parent / "roles.json"


@dataclass
class Player:
    """One player in a TIME WARS session. Maps to TIMER player + role + inventory + mana."""
    agent_id: str
    time_remaining_sec: int
    role_id: str
    inventory: List[dict] = field(default_factory=list)  # list of code items: card or {"code_id", "seconds"} legacy
    status: str = "active"  # active | eliminated
    mana: float = 20.0  # trust = mana; start 20, accumulates per round
    core_params: dict = field(default_factory=dict)  # loaded from agents/{id}/CORE.json

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "time_remaining_sec": self.time_remaining_sec,
            "role_id": self.role_id,
            "inventory": list(self.inventory),
            "status": self.status,
            "mana": self.mana,
        }

    def cooperation_bias(self) -> float:
        """0.0–1.0; from CORE.json (0–100 scale)."""
        return min(1.0, float(self.core_params.get("cooperation_bias", 50)) / 100)

    def deception_tendency(self) -> float:
        """0.0–1.0; from CORE.json (0–100 scale)."""
        return min(1.0, float(self.core_params.get("deception_tendency", 50)) / 100)

    def risk_appetite(self) -> float:
        """0.0–1.0; from CORE.json (0–100 scale)."""
        return min(1.0, float(self.core_params.get("risk_appetite", 50)) / 100)


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


def _load_agent_core(agent_id: str, agents_dir: Optional[Path] = None) -> dict:
    """Load CORE.json for agent. Returns {} if not found."""
    base = agents_dir or (Path(__file__).resolve().parents[2] / "agents")
    p = base / agent_id / "CORE.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _load_agent_memory(agent_id: str, agents_dir: Optional[Path] = None) -> dict:
    """Load MEMORY.json for agent. Returns {} if not found."""
    base = agents_dir or (Path(__file__).resolve().parents[2] / "agents")
    p = base / agent_id / "MEMORY.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _core_similarity(core_a: dict, core_b: dict) -> float:
    """
    Cosine similarity of numeric personality params between two agents.
    Higher similarity → higher initial trust.
    Returns 0.3–0.7 range (neutral zone).
    """
    keys = ["cooperation_bias", "deception_tendency", "strategic_horizon", "risk_appetite"]
    va = [float(core_a.get(k, 50)) for k in keys]
    vb = [float(core_b.get(k, 50)) for k in keys]
    dot = sum(x * y for x, y in zip(va, vb))
    norm_a = math.sqrt(sum(x * x for x in va)) or 1.0
    norm_b = math.sqrt(sum(y * y for y in vb)) or 1.0
    cos = dot / (norm_a * norm_b)
    # Map cosine similarity (−1..1) to trust range (0.3..0.7)
    return round(0.3 + (cos + 1) / 2 * 0.4, 3)


def init_trust_from_memory(
    session: "Session",
    agents_dir: Optional[Path] = None,
) -> None:
    """
    Override flat 0.5 trust with cross-game data:
    1. If MEMORY.json has trust_history[target_id] → use it directly.
    2. Else if both have CORE.json → cosine similarity of personality params.
    3. Else → keep 0.5.
    Also loads each agent's CORE.json into player.core_params for later use.
    """
    agent_ids = [p.agent_id for p in session.players]
    cores: Dict[str, dict] = {aid: _load_agent_core(aid, agents_dir) for aid in agent_ids}
    memories: Dict[str, dict] = {aid: _load_agent_memory(aid, agents_dir) for aid in agent_ids}

    # Store core params on player objects for utility function access
    for p in session.players:
        p.core_params = cores.get(p.agent_id, {})

    for a in agent_ids:
        mem_a = memories.get(a, {})
        trust_hist = mem_a.get("trust_history", {})
        for b in agent_ids:
            if a == b:
                continue
            if b in trust_hist:
                # Direct cross-game trust
                val = float(trust_hist[b])
                session.set_trust(a, b, max(0.0, min(1.0, val)))
            elif cores.get(a) and cores.get(b):
                # Personality similarity as proxy
                sim = _core_similarity(cores[a], cores[b])
                session.set_trust(a, b, sim)
            # else stays at 0.5 default


def save_trust_to_memory(
    session: "Session",
    agents_dir: Optional[Path] = None,
) -> None:
    """
    Persist final trust values back to each agent's MEMORY.json trust_history
    after a game ends.
    """
    base = agents_dir or (Path(__file__).resolve().parents[2] / "agents")
    for p in session.players:
        mem_path = base / p.agent_id / "MEMORY.json"
        if not mem_path.exists():
            continue
        try:
            mem = json.loads(mem_path.read_text(encoding="utf-8"))
            trust_hist = mem.get("trust_history", {})
            for o in session.players:
                if o.agent_id == p.agent_id:
                    continue
                # Exponential moving average: blend new with old
                old = float(trust_hist.get(o.agent_id, 0.5))
                new = session.get_trust(p.agent_id, o.agent_id)
                blended = round(0.7 * old + 0.3 * new, 4)
                trust_hist[o.agent_id] = blended
            mem["trust_history"] = trust_hist
            mem_path.write_text(json.dumps(mem, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass


def create_session(
    session_id: str,
    agent_ids: List[str],
    base_seconds_per_player: int = DEFAULT_BASE_SECONDS_PER_PLAYER,
    duration_limit_sec: Optional[int] = None,
    role_override: Optional[Dict[str, str]] = None,
    start_time: Optional[float] = None,
    agents_dir: Optional[Path] = None,
) -> "Session":
    """Create a new session with players and assigned roles. Trust from MEMORY/CORE."""
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
            mana=20.0,
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
    # Initialize trust between all pairs at 0.5, then override from memory
    for a in agent_ids:
        for b in agent_ids:
            if a != b:
                session.set_trust(a, b, 0.5)
    init_trust_from_memory(session, agents_dir)
    return session
