"""Cross-dialect column types.

`StringArray` is a list-of-text column that uses Postgres' native
`ARRAY(Text)` in production and falls back to `JSON` on SQLite so tests can
run against an in-memory database without a real Postgres.
"""

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.types import Text, TypeDecorator


class StringArray(TypeDecorator):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(Text))
        return dialect.type_descriptor(JSON())
