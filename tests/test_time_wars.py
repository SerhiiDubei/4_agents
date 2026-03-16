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


@test("time_wars: apply_before_steal_roll role_snake gives roll_bonus 2")
def _():
    from game_modes.time_wars.skills import apply_before_steal_roll
    r = apply_before_steal_roll("role_snake", {"actor_id": "a", "target_id": "b"})
    assert r.get("roll_bonus") == 2, f"expected roll_bonus 2, got {r}"


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


if __name__ == "__main__":
    print("TIME WARS tests")
    passed = sum(1 for r in results if r["status"] == PASS)
    failed = sum(1 for r in results if r["status"] == FAIL)
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
