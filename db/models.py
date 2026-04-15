"""
SQLAlchemy models for Time Wars persistent storage.
Tables: users, game_sessions, player_actions, human_decisions
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Float, DateTime, ForeignKey, Text, Boolean
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    decisions = relationship("HumanDecision", back_populates="user")


class GameSession(Base):
    __tablename__ = "game_sessions"

    id = Column(String, primary_key=True, default=_uuid)
    session_id = Column(String, unique=True, nullable=False, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    winner_id = Column(String, nullable=True)
    rounds = Column(Integer, nullable=True)
    ticks = Column(Integer, nullable=True)
    base_sec = Column(Integer, nullable=True)
    drain_base = Column(Integer, nullable=True)
    drain_double_every = Column(Integer, nullable=True)
    report_path = Column(String, nullable=True)
    has_human_player = Column(Boolean, default=False)
    human_player_id = Column(String, ForeignKey("users.id"), nullable=True)

    actions = relationship("PlayerAction", back_populates="session")
    decisions = relationship("HumanDecision", back_populates="session")


class PlayerAction(Base):
    __tablename__ = "player_actions"

    id = Column(String, primary_key=True, default=_uuid)
    session_id = Column(String, ForeignKey("game_sessions.session_id"), nullable=False, index=True)
    tick = Column(Integer, nullable=False)
    actor_id = Column(String, nullable=False)
    action_type = Column(String, nullable=False)   # steal / cooperate / pass / code_use
    target_id = Column(String, nullable=True)
    delta_sec = Column(Integer, nullable=True)
    outcome = Column(String, nullable=True)        # success / partial / fail / None
    roll = Column(Integer, nullable=True)

    session = relationship("GameSession", back_populates="actions")


class IslandGame(Base):
    """One completed Island simulation — stores per-agent stats for leaderboard."""
    __tablename__ = "island_games"

    id          = Column(String, primary_key=True, default=_uuid)
    game_id     = Column(String, unique=True, nullable=False, index=True)
    played_at   = Column(DateTime, default=datetime.utcnow, index=True)
    rounds      = Column(Integer, nullable=False)
    world_prompt = Column(Text, nullable=True)
    winner_id   = Column(String, nullable=True)
    winner_name = Column(String, nullable=True)
    # JSON list of {agent_id, name, score, coop_count, betray_count, neutral_count}
    agents_json = Column(Text, nullable=False)


class HumanDecision(Base):
    """Stores every decision a human player makes — used as ML training data."""
    __tablename__ = "human_decisions"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(String, ForeignKey("game_sessions.session_id"), nullable=False, index=True)
    tick = Column(Integer, nullable=False)
    action_type = Column(String, nullable=False)
    target_id = Column(String, nullable=True)
    context_json = Column(Text, nullable=True)    # JSON snapshot of game state at decision moment
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="decisions")
    session = relationship("GameSession", back_populates="decisions")
