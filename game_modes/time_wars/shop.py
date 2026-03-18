"""
TIME WARS shop: load codes, get available codes for player, buy code (once per round).
Position gate (comeback): S-коди тільки для bottom-2. Position discount: знижка за останні місця.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import List, Optional

from game_modes.time_wars.state import Session

_CODES_PATH = Path(__file__).resolve().parent / "codes.json"


def load_codes(path: Optional[Path] = None) -> List[dict]:
    """Load code cards from codes.json. Returns list of card dicts."""
    p = path or _CODES_PATH
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def _player_rank_from_bottom(session: Session, player_id: str) -> int:
    """1 = last place (least time), 2 = second last, etc. By time_remaining_sec ascending then by order."""
    active = session.active_players()
    if not active:
        return 1
    # Sort by time ascending (lowest first); same time → stable order
    ordered = sorted(
        [(p.agent_id, p.time_remaining_sec) for p in active],
        key=lambda x: (x[1], x[0]),
    )
    for r, (aid, _) in enumerate(ordered, start=1):
        if aid == player_id:
            return r
    return len(ordered)


def _position_discount_multiplier(card: dict, rank_from_bottom: int) -> float:
    """Повертає множник ціни (1.0 = без знижки). rank_from_bottom: 1 = останній."""
    disc = card.get("position_discount")
    if isinstance(disc, dict) and disc.get("enabled"):
        if rank_from_bottom == 1:
            return float(disc.get("multiplier_if_last", 1.0))
        if rank_from_bottom == 2:
            return float(disc.get("multiplier_if_bottom2", 1.0))
        return 1.0
    # Legacy: flat position_modifier
    mod = card.get("position_modifier")
    if isinstance(mod, (int, float)):
        return float(mod)
    return 1.0


def effective_cost(card: dict, session: Session, player_id: str) -> float:
    """Ціна коду з урахуванням position discount."""
    base = float(card.get("cost_mana", 0))
    rank = _player_rank_from_bottom(session, player_id)
    mult = _position_discount_multiplier(card, rank)
    return max(1, round(base * mult))


def _position_gate_allowed(card: dict, rank_from_bottom: int) -> bool:
    """Чи дозволено купувати код з position_gate (тільки для bottom-K)."""
    gate = card.get("position_gate")
    if isinstance(gate, dict) and gate.get("enabled"):
        allowed = int(gate.get("allowed_ranks_from_bottom", 1))
        return rank_from_bottom <= allowed
    if card.get("position_gated") is True:
        return rank_from_bottom <= 2  # default: bottom-2
    return True


def get_available_codes(
    session: Session,
    player_id: str,
    codes: Optional[List[dict]] = None,
) -> List[dict]:
    """
    Return codes the player can afford (mana >= effective cost) and that pass position_gate.
    """
    player = session.get_player(player_id)
    if not player or player.status != "active":
        return []
    if codes is None:
        codes = load_codes()
    rank = _player_rank_from_bottom(session, player_id)
    available = []
    for card in codes:
        if not _position_gate_allowed(card, rank):
            continue
        cost = effective_cost(card, session, player_id)
        if cost <= player.mana:
            available.append(card)
    return available


def buy_code(
    session: Session,
    player_id: str,
    code_id: str,
    codes: Optional[List[dict]] = None,
) -> bool:
    """
    If player has enough mana, subtract effective cost (with position discount), add card to inventory.
    """
    player = session.get_player(player_id)
    if not player or player.status != "active":
        return False
    if codes is None:
        codes = load_codes()
    card = next((c for c in codes if c.get("id") == code_id), None)
    if not card:
        return False
    if not _position_gate_allowed(card, _player_rank_from_bottom(session, player_id)):
        return False
    cost = effective_cost(card, session, player_id)
    if player.mana < cost:
        return False
    player.mana -= cost
    player.inventory.append(copy.deepcopy(card))
    return True
