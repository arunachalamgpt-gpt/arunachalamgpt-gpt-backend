"""devotee_repeat_tracking — last_reply_hash, last_reply_at, repeat_count

Revision ID: a4f2c1d8e9b3
Revises: c7e6d26aaaef
Create Date: 2026-06-30 05:30:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'a4f2c1d8e9b3'
down_revision: Union[str, Sequence[str], None] = 'c7e6d26aaaef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'devotee_profiles',
        sa.Column(
            'last_reply_hash',
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=True,
        ),
    )
    op.add_column(
        'devotee_profiles',
        sa.Column('last_reply_at', sa.DateTime(), nullable=True),
    )
    op.add_column(
        'devotee_profiles',
        sa.Column(
            'repeat_count',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ),
    )


def downgrade() -> None:
    op.drop_column('devotee_profiles', 'repeat_count')
    op.drop_column('devotee_profiles', 'last_reply_at')
    op.drop_column('devotee_profiles', 'last_reply_hash')
