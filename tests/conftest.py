"""
conftest.py — shared pytest fixtures for Time Wars tests.

Provides ready-made Session objects so individual tests don't need boilerplate.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def mini_session():
    """4 players, 500 sec each — for fast unit tests."""
    from game_modes.time_wars.state import create_session
    from game_modes.time_wars.loop import log_game_start
    session = create_session(
        session_id="fixture_mini",
        agent_ids=["p_a", "p_b", "p_c", "p_d"],
        base_seconds_per_player=500,
        duration_limit_sec=2000,
    )
    log_game_start(session)
    return session


@pytest.fixture
def two_player_session():
    """2 players, 30 sec each — for fast elimination / termination tests."""
    from game_modes.time_wars.state import create_session
    from game_modes.time_wars.loop import log_game_start
    session = create_session(
        session_id="fixture_2p",
        agent_ids=["alpha", "beta"],
        base_seconds_per_player=30,
        duration_limit_sec=500,
    )
    log_game_start(session)
    return session


@pytest.fixture
def full_session():
    """6 players, 1000 sec each — mirrors the real production config."""
    from game_modes.time_wars.state import create_session
    from game_modes.time_wars.loop import log_game_start
    session = create_session(
        session_id="fixture_full",
        agent_ids=[
            "agent_synth_c", "agent_synth_d", "agent_synth_g",
            "agent_synth_h", "agent_synth_i", "agent_synth_j",
        ],
        base_seconds_per_player=1000,
        duration_limit_sec=2000,
    )
    log_game_start(session)
    return session
