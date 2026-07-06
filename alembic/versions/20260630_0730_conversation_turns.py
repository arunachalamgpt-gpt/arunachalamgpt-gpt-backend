"""conversation_turns — per-user chat memory for context-aware replies

Revision ID: b7d19f4a2c85
Revises: a4f2c1d8e9b3
Create Date: 2026-06-30 07:30:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'b7d19f4a2c85'
down_revision: Union[str, Sequence[str], None] = 'a4f2c1d8e9b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'conversation_turns',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('phone', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column('role', sqlmodel.sql.sqltypes.AutoString(length=10), nullable=False),
        sa.Column('text', sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=False),
        sa.Column('intent', sqlmodel.sql.sqltypes.AutoString(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_conversation_turns_phone'),
        'conversation_turns',
        ['phone'],
        unique=False,
    )
    op.create_index(
        op.f('ix_conversation_turns_created_at'),
        'conversation_turns',
        ['created_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_conversation_turns_created_at'),
        table_name='conversation_turns',
    )
    op.drop_index(
        op.f('ix_conversation_turns_phone'),
        table_name='conversation_turns',
    )
    op.drop_table('conversation_turns')
