"""
test_time_wars.py

Unit and integration tests for TIME WARS (game_modes/time_wars).
No changes to core game_engine or decision_engine.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PASS = "PASS"
FAIL = "FAIL"
results: list[dict] = []


def test(name: str):
    def decorator(fn):
        start = time.time()
        status = PASS
        error = ""
        try:
            fn()
        except AssertionError as e:
            status = FAIL
            error = str(e) or "Assertion failed"
        except Exception as e:
            status = FAIL
            error = f"{type(e).__name__}: {e}"
        elapsed = round((time.time() - start) * 1000)
        results.append({"name": name, "status": status, "ms": elapsed, "error": error})
        icon = "P" if status == PASS else "F"
        print(f"  {icon} [{status}] {name} ({elapsed}ms)" + (f" -> {error}" if error else ""))
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Unit: roles and skills
# ---------------------------------------------------------------------------

@test("time_wars: load roles returns list of roles")
def _():
    from game_modes.time_wars.state import load_roles
    data = load_roles()
    roles = data.get("roles", [])
    assert isinstance(roles, list), "roles should be a list"
    assert len(roles) >= 1, "at least one role"
    assert "id" in roles[0] and "skills" in roles[0], "role has id and skills"


@test("time_wars: get_skills_for_role returns skills for role_snake")
def _():
    from game_modes.time_wars.skills import get_skills_for_role
    skills_list = get_skills_for_role("role_snake")
    assert isinstance(skills_list, list)
    ids = [s.get("id") for s in skills_list]
    assert any("steal" in (id or "") or "snake" in (id or "") for id in ids), "snake has steal-related skill"


@test("time_wars: apply_before_steal_roll role_snake gives roll_bonus 1")
def _():
    # Snake nerf: roll_bonus 2 → 1 (balance v6, see SIMULATION_ANALYSIS.md fix A)
    from game_modes.time_wars.skills import apply_before_steal_roll
    r = apply_before_steal_roll("role_snake", {"actor_id": "a", "target_id": "b"})
    assert r.get("roll_bonus") == 1, f"expected roll_bonus 1, got {r}"


@test("time_wars: apply_on_steal_fail role_gambler gives penalty_override 25")
def _():
    from game_modes.time_wars.skills import apply_on_steal_fail
    r = apply_on_steal_fail("role_gambler", {"default_penalty_seconds": 15})
    assert r.get("penalty_override") == 25, f"expected 25, got {r}"


@test("time_wars: block_steal role_banker returns True")
def _():
    from game_modes.time_wars.skills import block_steal
    assert block_steal("role_banker") is True
    assert block_steal("role_snake") is False


# ---------------------------------------------------------------------------
# Unit: state and tick
# ---------------------------------------------------------------------------

@test("time_wars: create_session assigns roles and initial time")
def _():
    from game_modes.time_wars.state import create_session
    session = create_session("test_s1", ["a1", "a2", "a3"], base_seconds_per_player=100, duration_limit_sec=60)
    assert len(session.players) == 3
    for p in session.players:
        assert p.time_remaining_sec == 100
        assert p.role_id
        assert p.status == "active"


@test("time_wars: tick reduces time and eliminates at 0")
def _():
    from game_modes.time_wars.state import create_session
    from game_modes.time_wars.loop import tick, log_game_start
    session = create_session("test_tick", ["x", "y"], base_seconds_per_player=2, duration_limit_sec=10)
    log_game_start(session)
    session.get_player("x").time_remaining_sec = 1
    eliminated = tick(session, 1)
    assert session.get_player("x").time_remaining_sec == 0
    assert session.get_player("x").status == "eliminated"
    assert "x" in eliminated
    event_types = [e.get("event_type") for e in session.event_log]
    assert "elimination" in event_types


@test("time_wars: apply_cooperate adds time and logs")
def _():
    from game_modes.time_wars.state import create_session
    from game_modes.time_wars.loop import apply_cooperate, log_game_start
    session = create_session("test_coop", ["p1", "p2"], base_seconds_per_player=100, duration_limit_sec=10)
    log_game_start(session)
    ok = apply_cooperate(session, "p1", "p2", tick_num=5)
    assert ok is True
    assert session.get_player("p1").time_remaining_sec == 100 + 30
    assert session.get_player("p2").time_remaining_sec == 100 + 30
    event_types = [e.get("event_type") for e in session.event_log]
    assert "cooperate" in event_types


@test("time_wars: apply_steal resolves and logs")
def _():
    import random
    from game_modes.time_wars.state import create_session
    from game_modes.time_wars.loop import apply_steal, log_game_start
    session = create_session("test_steal", ["a", "b"], base_seconds_per_player=200, duration_limit_sec=10)
    log_game_start(session)
    rng = random.Random(42)
    out = apply_steal(session, "a", "b", tick_num=1, rng=rng)
    assert out["outcome"] in ("success", "partial", "fail")
    assert "actor_delta" in out and "target_delta" in out
    event_types = [e.get("event_type") for e in session.event_log]
    assert "steal" in event_types


# ---------------------------------------------------------------------------
# Integration: short run
# ---------------------------------------------------------------------------

@test("time_wars: write_session_log produces JSONL file")
def _():
    import tempfile
    from game_modes.time_wars.state import create_session
    from game_modes.time_wars.loop import log_game_start
    from game_modes.time_wars.logging_export import write_session_log
    session = create_session("log_test", ["x", "y"], base_seconds_per_player=10, duration_limit_sec=5)
    log_game_start(session)
    with tempfile.TemporaryDirectory() as d:
        path = write_session_log(session, Path(d))
        assert path.exists()
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 1
        import json
        first = json.loads(lines[0])
        assert first.get("event_type") in ("game_start", "role_assignment")


@test("time_wars: export_to_timer_events returns TIMER-shaped list")
def _():
    from game_modes.time_wars.state import create_session
    from game_modes.time_wars.loop import log_game_start
    from game_modes.time_wars.logging_export import export_to_timer_events
    session = create_session("export_test", ["a"], base_seconds_per_player=10, duration_limit_sec=5)
    log_game_start(session)
    events = export_to_timer_events(session)
    assert isinstance(events, list)
    assert len(events) >= 1
    assert "room_id" in events[0] and "event_type" in events[0]


# ---------------------------------------------------------------------------
# Code manifest
# ---------------------------------------------------------------------------

@test("time_wars: code_cost Vampire 1.5 steal risk 1.0 gives 39 or 40")
def _():
    from game_modes.time_wars.code_manifest import code_cost
    # no class_key → phi=1.0; (1.5*1.3*20)*1.0 = 39
    c = code_cost(1.5, "steal", risk_multiplier=1.0, position_modifier=1.0)
    assert c in (39, 40), f"expected 39 or 40, got {c}"


@test("time_wars: base_ev_from_cost 40 steal gives ~1.5")
def _():
    from game_modes.time_wars.code_manifest import base_ev_from_cost
    ev = base_ev_from_cost(40, "steal", 1.0, 1.0)
    assert 1.4 <= ev <= 1.6, f"expected ~1.5, got {ev}"


@test("time_wars: expected_value_eq self 1.0 single outcome")
def _():
    from game_modes.time_wars.ev_calc import expected_value_eq
    card = {"type": "self", "choices": [{"outcomes": [{"effect_self": 1.0, "probability": 1.0}]}]}
    ev = expected_value_eq(card, n=6)
    assert 0.99 <= ev <= 1.01, f"expected EV≈1.0, got {ev}"


@test("time_wars: suggested_price within class range")
def _():
    from game_modes.time_wars.ev_calc import suggested_price
    card = {"class": "b", "type": "self", "risk_level": 0,
            "choices": [{"outcomes": [{"effect_self": 1.0, "probability": 1.0}]}]}
    p = suggested_price(card, n=6)
    assert 18 <= p <= 30, f"b-class 1.0 self expected 18-30, got {p}"


@test("time_wars: validate_code returns ok and ev for valid card")
def _():
    from game_modes.time_wars.ev_calc import validate_code
    card = {"id": "t", "class": "c", "type": "self", "cost_mana": 12,
            "choices": [{"outcomes": [{"effect_self": 0.5, "probability": 1.0}]}]}
    out = validate_code(card, n=6)
    assert "ev" in out and "errors" in out
    assert out["ev"] > 0


@test("time_wars: effective_cost and position_discount")
def _():
    from game_modes.time_wars.state import create_session
    from game_modes.time_wars.shop import effective_cost, _player_rank_from_bottom
    session = create_session("shop_test", ["a", "b", "c"], base_seconds_per_player=100, duration_limit_sec=10)
    session.get_player("a").time_remaining_sec = 10
    session.get_player("b").time_remaining_sec = 50
    session.get_player("c").time_remaining_sec = 100
    rank_a = _player_rank_from_bottom(session, "a")
    assert rank_a == 1, "a has least time = last place"
    card = {"cost_mana": 20, "position_discount": {"enabled": True, "multiplier_if_last": 0.7, "multiplier_if_bottom2": 0.85}}
    cost_a = effective_cost(card, session, "a")
    assert cost_a == 14, f"20*0.7=14, got {cost_a}"


@test("time_wars: position_gate S-code only for bottom-2")
def _():
    from game_modes.time_wars.state import create_session
    from game_modes.time_wars.shop import get_available_codes
    session = create_session("gate_test", ["p1", "p2", "p3"], base_seconds_per_player=100, duration_limit_sec=10)
    session.get_player("p1").time_remaining_sec = 5
    session.get_player("p2").time_remaining_sec = 50
    session.get_player("p3").time_remaining_sec = 100
    session.get_player("p1").mana = 100
    session.get_player("p2").mana = 100
    session.get_player("p3").mana = 100
    codes = [
        {"id": "comeback", "cost_mana": 65, "position_gate": {"enabled": True, "allowed_ranks_from_bottom": 2}},
    ]
    avail_p1 = get_available_codes(session, "p1", codes)
    avail_p3 = get_available_codes(session, "p3", codes)
    assert len(avail_p1) == 1, "p1 (last) can see position_gated code"
    assert len(avail_p3) == 0, "p3 (leader) cannot see position_gated code"


@test("time_wars: segment_for_cost Budget and Premium")
def _():
    from game_modes.time_wars.code_manifest import segment_for_cost
    assert segment_for_cost(14) == "Budget"
    assert segment_for_cost(45) == "Premium"


@test("time_wars: validate_card valid card passes")
def _():
    from game_modes.time_wars.code_manifest import validate_card
    card = {
        "id": "test",
        "class": "c",
        "type": "self",
        "base_ev": 1,
        "cost_mana": 14,
        "choices": [{"id": "x", "outcomes": [{"effect_self": 1, "probability": 1.0}]}],
    }
    err = validate_card(card)
    assert err == [], f"expected no errors, got {err}"


@test("time_wars: apply_code_use with card choices applies effect_self")
def _():
    from game_modes.time_wars.state import create_session
    from game_modes.time_wars.loop import log_game_start, apply_code_use
    import random
    session = create_session("card_test", ["a", "b"], base_seconds_per_player=600, duration_limit_sec=10)
    log_game_start(session)
    card = {
        "id": "mini",
        "class": "c",
        "type": "self",
        "base_ev": 1,
        "cost_mana": 14,
        "choices": [{"id": "use", "outcomes": [{"effect_self": 1, "effect_other": 0, "probability": 1.0}]}],
    }
    session.get_player("a").inventory.append(card)
    ok = apply_code_use(session, "a", 0, 1, rng=random.Random(42))
    assert ok is True
    assert session.get_player("a").time_remaining_sec == 600 + 60  # +1 min = +60 sec
    assert "code_use" in [e.get("event_type") for e in session.event_log]


if __name__ == "__main__":
    print("TIME WARS tests")
    passed = sum(1 for r in results if r["status"] == PASS)
    failed = sum(1 for r in results if r["status"] == FAIL)
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
