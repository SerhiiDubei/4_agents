"""initial schema — users game_sessions player_actions island_games human_decisions

Revision ID: 9fe448526709
Revises:
Create Date: 2026-04-17 13:05:35.617805

Baseline міграція — знімок всієї схеми на момент введення Alembic.
Нові БД: `alembic upgrade head` створить всі таблиці.
Існуючі БД: `alembic stamp head` (запускається з db/init_alembic.py при старті сервера).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9fe448526709'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Створює всю схему БД. На існуючих БД викликати alembic stamp head."""
    bind = op.get_bind()

    # Перевіряємо які таблиці вже існують — не створюємо повторно
    existing = sa.inspect(bind).get_table_names()

    if 'users' not in existing:
        op.create_table(
            'users',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('username', sa.String(), nullable=False),
            sa.Column('email', sa.String(), nullable=False),
            sa.Column('password_hash', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
        with op.batch_alter_table('users', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_users_username'), ['username'], unique=True)
            batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=True)

    if 'game_sessions' not in existing:
        op.create_table(
            'game_sessions',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('session_id', sa.String(), nullable=False),
            sa.Column('started_at', sa.DateTime(), nullable=True),
            sa.Column('ended_at', sa.DateTime(), nullable=True),
            sa.Column('winner_id', sa.String(), nullable=True),
            sa.Column('rounds', sa.Integer(), nullable=True),
            sa.Column('ticks', sa.Integer(), nullable=True),
            sa.Column('base_sec', sa.Integer(), nullable=True),
            sa.Column('drain_base', sa.Integer(), nullable=True),
            sa.Column('drain_double_every', sa.Integer(), nullable=True),
            sa.Column('report_path', sa.String(), nullable=True),
            sa.Column('has_human_player', sa.Boolean(), nullable=True),
            sa.Column('human_player_id', sa.String(), sa.ForeignKey('users.id'), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
        with op.batch_alter_table('game_sessions', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_game_sessions_session_id'), ['session_id'], unique=True)

    if 'player_actions' not in existing:
        op.create_table(
            'player_actions',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('session_id', sa.String(), sa.ForeignKey('game_sessions.session_id'), nullable=False),
            sa.Column('tick', sa.Integer(), nullable=False),
            sa.Column('actor_id', sa.String(), nullable=False),
            sa.Column('action_type', sa.String(), nullable=False),
            sa.Column('target_id', sa.String(), nullable=True),
            sa.Column('delta_sec', sa.Integer(), nullable=True),
            sa.Column('outcome', sa.String(), nullable=True),
            sa.Column('roll', sa.Integer(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
        with op.batch_alter_table('player_actions', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_player_actions_session_id'), ['session_id'], unique=False)

    if 'island_games' not in existing:
        op.create_table(
            'island_games',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('game_id', sa.String(), nullable=False),
            sa.Column('played_at', sa.DateTime(), nullable=True),
            sa.Column('rounds', sa.Integer(), nullable=False),
            sa.Column('world_prompt', sa.Text(), nullable=True),
            sa.Column('winner_id', sa.String(), nullable=True),
            sa.Column('winner_name', sa.String(), nullable=True),
            sa.Column('agents_json', sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        with op.batch_alter_table('island_games', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_island_games_game_id'), ['game_id'], unique=True)
            batch_op.create_index(batch_op.f('ix_island_games_played_at'), ['played_at'], unique=False)

    if 'human_decisions' not in existing:
        op.create_table(
            'human_decisions',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('session_id', sa.String(), sa.ForeignKey('game_sessions.session_id'), nullable=False),
            sa.Column('tick', sa.Integer(), nullable=False),
            sa.Column('action_type', sa.String(), nullable=False),
            sa.Column('target_id', sa.String(), nullable=True),
            sa.Column('context_json', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
        with op.batch_alter_table('human_decisions', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_human_decisions_user_id'), ['user_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_human_decisions_session_id'), ['session_id'], unique=False)


def downgrade() -> None:
    """Видаляє всі таблиці (тільки якщо вони були створені цією міграцією)."""
    with op.batch_alter_table('human_decisions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_human_decisions_session_id'))
        batch_op.drop_index(batch_op.f('ix_human_decisions_user_id'))
    op.drop_table('human_decisions')

    with op.batch_alter_table('island_games', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_island_games_played_at'))
        batch_op.drop_index(batch_op.f('ix_island_games_game_id'))
    op.drop_table('island_games')

    with op.batch_alter_table('player_actions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_player_actions_session_id'))
    op.drop_table('player_actions')

    with op.batch_alter_table('game_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_game_sessions_session_id'))
    op.drop_table('game_sessions')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_email'))
        batch_op.drop_index(batch_op.f('ix_users_username'))
    op.drop_table('users')
