"""
test_tw_integration.py

pytest-compatible integration tests for TIME WARS.

Answers three critical questions every time you run:
  1. Does escalating_drain math actually double at the right ticks?
  2. Does every active agent get an action every single round?
  3. Does the battle royale end exactly when 1 player remains?
  4. Does cooperation stay net-neutral at drain=3?

Run:
    python -m pytest tests/test_tw_integration.py -v
    python -m pytest tests/test_tw_integration.py -v --tb=short
"""

from __future__ import annotations

import random
import sys
from collections import defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# 1. DRAIN MATH — escalating_drain formula correctness
# ---------------------------------------------------------------------------

class TestEscalatingDrainMath:
    """Verify that escalating_drain doubles at exactly the right tick boundaries."""

    def test_drain_base_value_ticks_1_to_N(self):
        """Drain equals base for all ticks in the first window."""
        from game_modes.time_wars.loop import escalating_drain
        base, every = 3, 200
        # All ticks 1..200 should return exactly 3
        for t in (1, 50, 100, 150, 200):
            assert escalating_drain(t, base, every) == 3, (
                f"Expected drain=3 at tick {t}, got {escalating_drain(t, base, every)}"
            )

    def test_drain_first_doubling_at_tick_201(self):
        """Drain doubles at tick double_every+1 (tick 201 with every=200)."""
        from game_modes.time_wars.loop import escalating_drain
        base, every = 3, 200
        assert escalating_drain(200, base, every) == 3,  "tick 200 should still be 3"
        assert escalating_drain(201, base, every) == 6,  "tick 201 should double to 6"

    def test_drain_second_doubling_at_tick_401(self):
        """Drain doubles again at tick 401 (x4 from base)."""
        from game_modes.time_wars.loop import escalating_drain
        base, every = 3, 200
        assert escalating_drain(400, base, every) == 6,  "tick 400 should still be 6"
        assert escalating_drain(401, base, every) == 12, "tick 401 should be 12"

    def test_drain_third_doubling_at_tick_601(self):
        """Drain is x8 after three windows."""
        from game_modes.time_wars.loop import escalating_drain
        base, every = 3, 200
        assert escalating_drain(601, base, every) == 24

    def test_drain_never_zero_or_negative(self):
        """Drain is always >= base for any positive tick."""
        from game_modes.time_wars.loop import escalating_drain
        base, every = 3, 200
        for t in range(1, 1001, 50):
            assert escalating_drain(t, base, every) >= base, f"drain went below base at tick {t}"

    def test_drain_with_small_every(self):
        """Works correctly with small double_every values (legacy / testing)."""
        from game_modes.time_wars.loop import escalating_drain
        # double_every=5: ticks 1-5 → 1, 6-10 → 2, 11-15 → 4
        assert escalating_drain(1,  1, 5) == 1
        assert escalating_drain(5,  1, 5) == 1
        assert escalating_drain(6,  1, 5) == 2
        assert escalating_drain(10, 1, 5) == 2
        assert escalating_drain(11, 1, 5) == 4


# ---------------------------------------------------------------------------
# 2. AGENT COVERAGE — every active agent acts every round
# ---------------------------------------------------------------------------

class TestAllAgentsActEveryRound:
    """
    Run a mini game loop for N rounds and verify:
      - Every active player produces exactly one player_intent per round.
      - No round is skipped.
      - When a player is eliminated, the count decreases correctly.
    """

    def _run_mini_game(self, n_rounds: int, base_sec: int = 500, drain: int = 1):
        """
        Run a tight game loop for n_rounds action rounds (each round = 10 ticks).
        Returns the full event_log.
        """
        from game_modes.time_wars.state import create_session
        from game_modes.time_wars.loop import (
            tick, escalating_drain,
            apply_cooperate, apply_steal,
            is_game_over, log_game_start, log_game_over,
            build_situation_text, log_round_start, log_player_intent,
        )
        from game_modes.time_wars.agent_context import get_agent_action_mock

        agent_ids = ["tw_a", "tw_b", "tw_c", "tw_d"]
        ticks_per_action = 10
        duration = n_rounds * ticks_per_action + 1
        rng = random.Random(42)

        session = create_session(
            session_id="integ_test",
            agent_ids=agent_ids,
            base_seconds_per_player=base_sec,
            duration_limit_sec=duration,
        )
        log_game_start(session)

        for t in range(1, duration + 1):
            drain_val = drain
            tick(session, t, drain_sec=drain_val)

            if is_game_over(session, t, min_ticks_before_elimination_win=ticks_per_action):
                log_game_over(session, t)
                break

            if t % ticks_per_action == 0:
                round_num = t // ticks_per_action
                sit = build_situation_text(session)
                sit["drain_sec"] = drain_val
                sit["drain_double_every"] = 200
                log_round_start(session, round_num, t, t, sit)

                for p in session.active_players():
                    act = get_agent_action_mock(session, p.agent_id, rng=rng)
                    log_player_intent(
                        session, p.agent_id, t,
                        thought=act.get("thought", ""),
                        plan=act.get("plan", ""),
                        choice=act.get("choice", ""),
                        reason=act.get("reason", ""),
                    )
                    if act["action"] == "cooperate" and act.get("target_id"):
                        apply_cooperate(session, p.agent_id, act["target_id"], t)
                    elif act["action"] == "steal" and act.get("target_id"):
                        apply_steal(session, p.agent_id, act["target_id"], t, rng=rng)

        return session

    def test_every_active_agent_has_intent_every_round(self):
        """
        For every round_start event: the number of player_intent events at that
        tick must equal the number of active players listed in round_start.
        Missing intents = agent silently skipped = BUG.
        """
        session = self._run_mini_game(n_rounds=5, base_sec=500, drain=1)
        events = session.event_log

        round_starts = [e for e in events if e.get("event_type") == "round_start"]
        intents = [e for e in events if e.get("event_type") == "player_intent"]

        intent_by_tick: dict[int, list[str]] = defaultdict(list)
        for e in intents:
            intent_by_tick[e.get("tick", 0)].append(e.get("agent_id", "?"))

        assert round_starts, "No round_start events found — game loop broken"

        for rs in round_starts:
            tick_num = rs.get("tick", 0)
            active = [p for p in rs.get("players", []) if p.get("status") == "active"]
            got_intents = intent_by_tick.get(tick_num, [])

            assert len(got_intents) == len(active), (
                f"Round {rs.get('round_num')} tick={tick_num}: "
                f"expected {len(active)} intents, got {len(got_intents)}. "
                f"Active: {[p['agent_id'] for p in active]}, "
                f"Got intents: {got_intents}"
            )

    def test_no_duplicate_intents_per_agent_per_round(self):
        """Each agent should appear at most once per round tick."""
        session = self._run_mini_game(n_rounds=5, base_sec=500, drain=1)
        events = session.event_log

        round_starts = [e for e in events if e.get("event_type") == "round_start"]
        intents = [e for e in events if e.get("event_type") == "player_intent"]

        intent_by_tick: dict[int, list[str]] = defaultdict(list)
        for e in intents:
            intent_by_tick[e.get("tick", 0)].append(e.get("agent_id", "?"))

        for rs in round_starts:
            tick_num = rs.get("tick", 0)
            agents = intent_by_tick.get(tick_num, [])
            assert len(agents) == len(set(agents)), (
                f"Round {rs.get('round_num')} tick={tick_num}: duplicate intents — "
                f"agents acted twice: {agents}"
            )

    def test_eliminated_agents_do_not_get_intents(self):
        """
        Drain enough to kill some players. After elimination, they must NOT
        appear in subsequent player_intent events.
        """
        # drain=45: each of 10 ticks = 450 sec/round; players start at 500
        # → all eliminated after round 2
        session = self._run_mini_game(n_rounds=10, base_sec=500, drain=45)
        events = session.event_log

        eliminations: set[str] = set()
        for e in events:
            if e.get("event_type") == "elimination":
                eliminations.add(e.get("target_id", ""))

        intents = [e for e in events if e.get("event_type") == "player_intent"]
        round_starts = [e for e in events if e.get("event_type") == "round_start"]

        if not eliminations or not round_starts:
            pytest.skip("No eliminations happened — increase drain or decrease base_sec")

        # Build: for each tick, which agents were already eliminated BEFORE this round
        tick_of_elimination: dict[str, int] = {}
        for e in events:
            if e.get("event_type") == "elimination":
                aid = e.get("target_id", "")
                t = e.get("tick", 0)
                tick_of_elimination[aid] = min(tick_of_elimination.get(aid, 9999), t)

        for e in intents:
            aid = e.get("agent_id", "")
            t = e.get("tick", 0)
            if aid in tick_of_elimination:
                assert t <= tick_of_elimination[aid], (
                    f"Eliminated agent {aid} (at tick {tick_of_elimination[aid]}) "
                    f"still produced intent at tick {t} — ghost acting!"
                )

    def test_round_count_matches_ticks(self):
        """round_num in round_start events must be sequential and match tick/10."""
        session = self._run_mini_game(n_rounds=5, base_sec=500, drain=1)
        round_starts = [e for e in session.event_log if e.get("event_type") == "round_start"]

        for rs in round_starts:
            expected_round = rs.get("tick", 0) // 10
            actual_round = rs.get("round_num", -1)
            assert actual_round == expected_round, (
                f"round_num={actual_round} does not match tick={rs.get('tick')} // 10 = {expected_round}"
            )


# ---------------------------------------------------------------------------
# 3. BATTLE ROYALE — termination logic
# ---------------------------------------------------------------------------

class TestBattleRoyaleTermination:
    """Verify that is_game_over / the game loop ends at exactly 1 player."""

    def test_game_over_when_one_player_remains(self):
        """is_game_over returns True as soon as active_players() == 1."""
        from game_modes.time_wars.state import create_session
        from game_modes.time_wars.loop import tick, is_game_over, log_game_start

        session = create_session(
            session_id="br_test",
            agent_ids=["x", "y"],
            base_seconds_per_player=5,
            duration_limit_sec=100,
        )
        log_game_start(session)
        session.get_player("x").time_remaining_sec = 1

        # tick 1: x loses 2 → x eliminated, y has 3 left
        tick(session, 1, drain_sec=2)
        assert session.get_player("x").status == "eliminated"
        assert session.get_player("y").status == "active"
        assert is_game_over(session, current_tick=1, min_ticks_before_elimination_win=1)

    def test_game_over_not_triggered_with_two_players(self):
        """is_game_over returns False when 2 players are alive."""
        from game_modes.time_wars.state import create_session
        from game_modes.time_wars.loop import is_game_over, log_game_start

        session = create_session(
            session_id="br_not_over",
            agent_ids=["a", "b"],
            base_seconds_per_player=100,
            duration_limit_sec=500,
        )
        log_game_start(session)
        assert not is_game_over(session, current_tick=1)

    def test_game_over_zero_players(self):
        """is_game_over returns True if ALL players are eliminated (draw)."""
        from game_modes.time_wars.state import create_session
        from game_modes.time_wars.loop import tick, is_game_over, log_game_start

        session = create_session(
            session_id="br_zero",
            agent_ids=["m", "n"],
            base_seconds_per_player=3,
            duration_limit_sec=100,
        )
        log_game_start(session)
        tick(session, 1, drain_sec=3)
        # Both die simultaneously
        assert session.get_player("m").status == "eliminated"
        assert session.get_player("n").status == "eliminated"
        assert is_game_over(session, current_tick=1)

    def test_game_ends_before_duration_cap(self):
        """Full loop: game ends by elimination, not by reaching duration_limit_sec."""
        from game_modes.time_wars.state import create_session
        from game_modes.time_wars.loop import (
            tick, is_game_over, log_game_start, log_game_over,
        )

        session = create_session(
            session_id="br_cap",
            agent_ids=["p1", "p2", "p3"],
            base_seconds_per_player=15,
            duration_limit_sec=1000,
        )
        log_game_start(session)

        ended_at = None
        for t in range(1, 1001):
            tick(session, t, drain_sec=5)
            if is_game_over(session, t):
                log_game_over(session, t)
                ended_at = t
                break

        assert ended_at is not None, "Game never ended — termination logic broken"
        assert ended_at < 1000, (
            f"Game reached duration cap (tick {ended_at}) instead of ending by elimination"
        )
        game_over_events = [e for e in session.event_log if e.get("event_type") == "game_over"]
        assert game_over_events, "game_over event was not logged"
        assert game_over_events[0].get("tick") == ended_at

    def test_winner_id_set_in_game_over(self):
        """log_game_over sets winner_id to the last surviving player."""
        from game_modes.time_wars.state import create_session
        from game_modes.time_wars.loop import (
            tick, is_game_over, log_game_start, log_game_over,
        )

        session = create_session(
            session_id="br_winner",
            agent_ids=["loser1", "loser2", "winner"],
            base_seconds_per_player=10,
            duration_limit_sec=500,
        )
        log_game_start(session)
        # Give winner a head start
        session.get_player("winner").time_remaining_sec = 300

        ended_at = None
        for t in range(1, 501):
            tick(session, t, drain_sec=5)
            if is_game_over(session, t):
                active = session.active_players()
                winner = active[0].agent_id if len(active) == 1 else None
                log_game_over(session, t, winner_id=winner)
                ended_at = t
                break

        go = next(e for e in session.event_log if e.get("event_type") == "game_over")
        assert go.get("winner_id") == "winner", (
            f"Expected 'winner' as winner_id, got {go.get('winner_id')!r}"
        )


# ---------------------------------------------------------------------------
# 4. COOPERATION NET-ZERO — drain=3 keeps game alive
# ---------------------------------------------------------------------------

class TestCoopNetZeroWithDrain3:
    """
    With drain=3/tick and 10 ticks/round, each round drains 30 sec.
    A full-coop round: both players get +30 each (COOP_REWARD_EACH=30).
    Net = 30 - 30 = 0. Players should NOT die from cooperation alone.
    """

    def test_coop_offsets_drain_exactly(self):
        """
        After 1 round (10 drain ticks + 1 coop action):
        time_after >= time_before - 30  (drain) + 30 (coop) = time_before.
        Players should survive indefinitely if they always cooperate.
        """
        from game_modes.time_wars.state import create_session
        from game_modes.time_wars.loop import tick, apply_cooperate, log_game_start
        from game_modes.time_wars.constants import COOP_REWARD_EACH

        session = create_session(
            session_id="coop_net",
            agent_ids=["alice", "bob"],
            base_seconds_per_player=200,
            duration_limit_sec=10000,
        )
        log_game_start(session)
        start_time = session.get_player("alice").time_remaining_sec

        # Simulate 1 round: 10 drain ticks at drain=3
        for t in range(1, 11):
            tick(session, t, drain_sec=3)

        time_after_drain = session.get_player("alice").time_remaining_sec
        assert time_after_drain == start_time - 30, (
            f"After 10 ticks drain=3, expected {start_time - 30}, got {time_after_drain}"
        )

        # Now coop
        apply_cooperate(session, "alice", "bob", tick_num=10)
        time_after_coop = session.get_player("alice").time_remaining_sec
        assert time_after_coop == start_time - 30 + COOP_REWARD_EACH, (
            f"After coop, expected {start_time - 30 + COOP_REWARD_EACH}, got {time_after_coop}"
        )

    def test_full_coop_players_survive_20_rounds(self):
        """
        If both players coop every round with drain=3, they should survive
        at least 20 rounds (net ~= 0 per round).
        """
        from game_modes.time_wars.state import create_session
        from game_modes.time_wars.loop import (
            tick, apply_cooperate, is_game_over, log_game_start,
        )

        session = create_session(
            session_id="coop_survive",
            agent_ids=["alice", "bob"],
            base_seconds_per_player=500,
            duration_limit_sec=10000,
        )
        log_game_start(session)

        alive_rounds = 0
        for t in range(1, 10001):
            tick(session, t, drain_sec=3)
            if is_game_over(session, t):
                break
            if t % 10 == 0:
                alive_rounds += 1
                for p in session.active_players():
                    others = [o for o in session.active_players() if o.agent_id != p.agent_id]
                    if others:
                        apply_cooperate(session, p.agent_id, others[0].agent_id, t)

        assert alive_rounds >= 20, (
            f"Players died after only {alive_rounds} rounds with full cooperation — "
            "coop is NOT offsetting drain=3"
        )

    def test_steal_creates_time_spread(self):
        """
        After repeated steals, the winner should have significantly more time
        than the loser — steals create meaningful differentiation.
        """
        import random as rnd
        from game_modes.time_wars.state import create_session
        from game_modes.time_wars.loop import (
            tick, apply_steal, is_game_over, log_game_start,
        )

        session = create_session(
            session_id="steal_spread",
            agent_ids=["thief", "victim"],
            base_seconds_per_player=1000,
            duration_limit_sec=10000,
        )
        log_game_start(session)

        rng = rnd.Random(1337)
        for t in range(1, 201):
            tick(session, t, drain_sec=1)
            if is_game_over(session, t):
                break
            if t % 10 == 0:
                if (session.get_player("thief").status == "active"
                        and session.get_player("victim").status == "active"):
                    apply_steal(session, "thief", "victim", t, rng=rng)

        thief_time = session.get_player("thief").time_remaining_sec
        victim_time = session.get_player("victim").time_remaining_sec

        if session.get_player("thief").status == "active":
            assert thief_time > victim_time, (
                f"After 20 steal rounds, thief ({thief_time}s) should have "
                f"more time than victim ({victim_time}s)"
            )
