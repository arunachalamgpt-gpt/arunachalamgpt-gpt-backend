"""Alembic environment.

Reads the DB URL from `app.config` (which loads `.env`) and registers
`SQLModel.metadata` so autogenerate sees every model in `app.models`.

The URL is passed straight to `create_engine` to bypass configparser's `%`
interpolation (otherwise URL-encoded characters like `%40` blow up).
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool
from sqlmodel import SQLModel

import app.models  # noqa: F401 — register tables
from app.config import DB_CONNECTION_STRING

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Generate SQL without connecting to a DB."""
    context.configure(
        url=DB_CONNECTION_STRING,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the configured DB and apply migrations."""
    connectable = create_engine(DB_CONNECTION_STRING, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
