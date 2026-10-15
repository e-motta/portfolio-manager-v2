"""SQLite dedupe in migration 039 keeps the oldest created_at (ties by id)."""

from sqlalchemy import text

from app.models.user import User
from sqlmodel import select


_DELETE_SQL = """
DELETE FROM {table}
WHERE external_id IS NOT NULL
  AND EXISTS (
    SELECT 1
    FROM {table} AS keeper
    WHERE keeper.external_id IS NOT NULL
      AND keeper.user_id = {table}.user_id
      AND keeper.external_id = {table}.external_id
      AND (
        keeper.created_at < {table}.created_at
        OR (
          keeper.created_at = {table}.created_at
          AND keeper.id < {table}.id
        )
      )
  )
"""


def test_sqlite_dedupe_keeps_oldest_created_at_then_lower_id(session):
    user = session.exec(select(User)).one()
    session.exec(
        text(
            """
            CREATE TABLE finance_expense_entries_dedupe_test (
                id TEXT,
                user_id TEXT,
                created_at TEXT,
                external_id TEXT,
                vendor TEXT
            )
            """
        )
    )
    try:
        session.exec(
            text(
                """
                INSERT INTO finance_expense_entries_dedupe_test
                    (id, user_id, created_at, external_id, vendor)
                VALUES
                    ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', :user_id,
                     '2026-06-02 10:00:00', 'pluggy:keep', 'Newer'),
                    ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', :user_id,
                     '2026-06-01 10:00:00', 'pluggy:keep', 'Older'),
                    ('dddddddd-dddd-dddd-dddd-dddddddddddd', :user_id,
                     '2026-06-03 10:00:00', 'pluggy:tie', 'Later id'),
                    ('cccccccc-cccc-cccc-cccc-cccccccccccc', :user_id,
                     '2026-06-03 10:00:00', 'pluggy:tie', 'Earlier id')
                """
            ),
            params={"user_id": str(user.id)},
        )
        session.exec(text(_DELETE_SQL.format(table="finance_expense_entries_dedupe_test")))
        rows = {
            row[0]: row[1]
            for row in session.exec(
                text("SELECT external_id, vendor FROM finance_expense_entries_dedupe_test")
            ).all()
        }
        assert rows == {"pluggy:keep": "Older", "pluggy:tie": "Earlier id"}
    finally:
        session.exec(text("DROP TABLE IF EXISTS finance_expense_entries_dedupe_test"))
