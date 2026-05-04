"""
database.py - PostgreSQL database layer for ExpenSOS.

All data persistence uses PostgreSQL via psycopg2.  A lightweight
ConnectionWrapper normalises the psycopg2 connection so the rest of the
application can call .execute(), .commit(), .rollback(), and .close()
without importing psycopg2 directly.
"""

import os
import time
from urllib.parse import urlparse

import psycopg2
from psycopg2 import extras

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)

# Local socket directory created by scripts/start_local_db.sh
LOCAL_PG_SOCKET_DIR = os.path.join(ROOT_DIR, ".local_pgsocket")
LOCAL_PG_PORT = os.environ.get("PGPORT", "55432")

# Default URL when running inside Docker Compose
DEFAULT_DOCKER_DATABASE_URL = "postgresql://expensos:expensos@db:5432/expensos"

# Kept for optional migration helper (see migrate_sqlite_to_postgres.py)
SQLITE_DB_PATH = os.path.join(BASE_DIR, "data", "expenses.db")


class ConnectionWrapper:
    """
    Thin wrapper around a psycopg2 connection that exposes a minimal,
    sqlite3-compatible API used throughout app.py.

    Every call to .execute() uses psycopg2's DictCursor so that result rows
    support both integer indexing (row[0]) and key-based access (row['id']).
    """

    def __init__(self, conn):
        self._conn = conn

    def execute(self, query, params=None):
        cursor = self._conn.cursor(cursor_factory=extras.DictCursor)
        cursor.execute(query, params or ())
        return cursor

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    # Context-manager support so callers can use `with get_db_connection() as conn:`
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        self.close()
        return False


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def _get_database_urls() -> list:
    """
    Return an ordered list of PostgreSQL connection URLs to try.

    Priority:
      1. DATABASE_URL environment variable (explicit configuration always wins).
         If the configured host is not "db" (the Docker Compose service name),
         we stop here – no point trying other URLs.
      2. Unix-domain socket to a locally-started Postgres instance (dev only).
      3. TCP localhost on the default port (dev / CI).
      4. Docker Compose service name "db" (fallback inside containers).
    """
    configured_url = os.environ.get("DATABASE_URL", "").strip()
    database_urls: list = []
    seen: set = set()

    def add(url: str) -> None:
        if url and url not in seen:
            seen.add(url)
            database_urls.append(url)

    if configured_url:
        add(configured_url)
        try:
            configured_host = urlparse(configured_url).hostname or ""
        except Exception:
            configured_host = ""
        # If an explicit, non-Docker URL was provided, trust it exclusively.
        if configured_host and configured_host not in ("db", ""):
            return database_urls

    # Local-socket connection (created by scripts/start_local_db.sh)
    if os.path.isdir(LOCAL_PG_SOCKET_DIR):
        add(
            f"postgresql://expensos@/expensos"
            f"?host={LOCAL_PG_SOCKET_DIR}&port={LOCAL_PG_PORT}"
        )

    add("postgresql://expensos:expensos@localhost:5432/expensos")
    add(DEFAULT_DOCKER_DATABASE_URL)

    return database_urls


def get_db_connection() -> ConnectionWrapper:
    """
    Return an open, wrapped PostgreSQL connection.

    Tries each URL from _get_database_urls() with up to DB_CONNECT_RETRIES
    attempts, sleeping DB_CONNECT_DELAY seconds between failures.  Raises
    RuntimeError if no connection could be established.
    """
    retries = int(os.environ.get("DB_CONNECT_RETRIES", "10"))
    delay = float(os.environ.get("DB_CONNECT_DELAY", "1.0"))
    last_error: Exception | None = None

    for url in _get_database_urls():
        for attempt in range(retries):
            try:
                raw_conn = psycopg2.connect(url)
                return ConnectionWrapper(raw_conn)
            except psycopg2.OperationalError as exc:
                last_error = exc
                if attempt < retries - 1:
                    time.sleep(delay)
                # Try the next attempt in the inner loop

    raise RuntimeError(
        f"Failed to connect to PostgreSQL after exhausting all URLs. "
        f"Last error: {last_error}"
    )


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

def init_db() -> None:
    """
    Create all tables (if they don't already exist) and seed the database
    with a default admin user when it is brand new.

    Safe to call on every application start – all DDL uses IF NOT EXISTS.
    """
    with get_db_connection() as conn:
        # -- users -----------------------------------------------------------
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            SERIAL PRIMARY KEY,
                username      TEXT NOT NULL UNIQUE,
                email         TEXT UNIQUE,
                mobile        TEXT UNIQUE,
                password_hash TEXT,
                otp           TEXT,
                otp_expiry    TIMESTAMP,
                is_verified   BOOLEAN NOT NULL DEFAULT FALSE,
                created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        ).close()

        # -- user_settings ---------------------------------------------------
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                id        SERIAL PRIMARY KEY,
                user_id   INTEGER NOT NULL UNIQUE
                              REFERENCES users(id) ON DELETE CASCADE,
                currency  TEXT NOT NULL DEFAULT '₹',
                theme     TEXT NOT NULL DEFAULT 'dark',
                language  TEXT NOT NULL DEFAULT 'en',
                font_size TEXT NOT NULL DEFAULT 'medium'
            )
            """
        ).close()

        # -- expenses --------------------------------------------------------
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id           SERIAL PRIMARY KEY,
                user_id      INTEGER NOT NULL DEFAULT 1
                                 REFERENCES users(id) ON DELETE CASCADE,
                amount       NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
                category     TEXT NOT NULL,
                note         TEXT,
                date         DATE NOT NULL,
                receipt_path TEXT,
                is_recurring BOOLEAN NOT NULL DEFAULT FALSE
            )
            """
        ).close()

        # -- budgets ---------------------------------------------------------
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS budgets (
                id         SERIAL PRIMARY KEY,
                user_id    INTEGER NOT NULL DEFAULT 1
                               REFERENCES users(id) ON DELETE CASCADE,
                category   TEXT NOT NULL,
                amount     NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
                period     TEXT NOT NULL DEFAULT 'monthly'
                               CHECK (period IN ('monthly', 'weekly')),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        ).close()

        # -- recurring_expenses ----------------------------------------------
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recurring_expenses (
                id         SERIAL PRIMARY KEY,
                user_id    INTEGER NOT NULL DEFAULT 1
                               REFERENCES users(id) ON DELETE CASCADE,
                amount     NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
                category   TEXT NOT NULL,
                note       TEXT,
                frequency  TEXT NOT NULL
                               CHECK (frequency IN ('daily', 'weekly', 'monthly')),
                next_date  DATE NOT NULL,
                active     BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        ).close()

        # -- reminders -------------------------------------------------------
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id             SERIAL PRIMARY KEY,
                user_id        INTEGER NOT NULL DEFAULT 1
                                   REFERENCES users(id) ON DELETE CASCADE,
                message        TEXT NOT NULL,
                remind_date    DATE NOT NULL,
                active         BOOLEAN NOT NULL DEFAULT TRUE,
                created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        ).close()

        # -- indexes (created with IF NOT EXISTS via DO block) ---------------
        _create_indexes(conn)

        # -- seed default admin user if DB is empty --------------------------
        cursor = conn.execute("SELECT COUNT(*) AS count FROM users")
        user_count = cursor.fetchone()["count"]
        cursor.close()

        if user_count == 0:
            from werkzeug.security import generate_password_hash

            cursor = conn.execute(
                """
                INSERT INTO users (username, email, password_hash, is_verified)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                ("admin", "admin@example.com", generate_password_hash("admin123"), True),
            )
            admin_id = cursor.fetchone()["id"]
            cursor.close()

            conn.execute(
                """
                INSERT INTO user_settings (user_id, currency, theme, language, font_size)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (admin_id, "₹", "dark", "en", "medium"),
            ).close()

        conn.commit()


def _create_indexes(conn: ConnectionWrapper) -> None:
    """Create performance indexes using DO blocks so they are idempotent."""
    index_statements = [
        ("idx_expenses_user_id",        "expenses(user_id)"),
        ("idx_expenses_user_date",       "expenses(user_id, date DESC)"),
        ("idx_expenses_user_category",   "expenses(user_id, category)"),
        ("idx_budgets_user_id",          "budgets(user_id)"),
        ("idx_budgets_user_category",    "budgets(user_id, category)"),
        ("idx_recurring_user_id",        "recurring_expenses(user_id)"),
        ("idx_reminders_user_id",        "reminders(user_id)"),
        ("idx_user_settings_user_id",    "user_settings(user_id)"),
    ]
    for idx_name, idx_cols in index_statements:
        conn.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_indexes WHERE indexname = '{idx_name}'
                ) THEN
                    CREATE INDEX {idx_name} ON {idx_cols};
                END IF;
            END $$;
            """
        ).close()


# ---------------------------------------------------------------------------
# Settings helper
# ---------------------------------------------------------------------------

def get_user_settings(user_id: int) -> dict:
    """
    Return user preference settings as a plain dict.

    Falls back to sensible defaults if no row exists (e.g. during
    unauthenticated requests).
    """
    _defaults = {
        "currency": "₹",
        "theme": "dark",
        "language": "en",
        "font_size": "medium",
    }
    if not user_id:
        return _defaults

    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT currency, theme, language, font_size "
            "FROM user_settings WHERE user_id = %s",
            (user_id,),
        )
        row = cursor.fetchone()
        cursor.close()

    if row:
        return dict(row)
    return _defaults


# ---------------------------------------------------------------------------
# Optional: SQLite → PostgreSQL migration helper
# ---------------------------------------------------------------------------

def migrate_sqlite_to_postgres(sqlite_path: str = SQLITE_DB_PATH) -> None:
    """
    One-shot migration: copy all rows from a SQLite database into PostgreSQL.

    The destination tables are truncated first (RESTART IDENTITY CASCADE) so
    this is safe to re-run for a clean import, but will erase any existing
    PostgreSQL data.
    """
    import sqlite3  # only imported when the migration helper is actually used

    init_db()

    source = sqlite3.connect(sqlite_path)
    source.row_factory = sqlite3.Row

    table_order = [
        "users",
        "user_settings",
        "expenses",
        "budgets",
        "recurring_expenses",
        "reminders",
    ]

    with get_db_connection() as dest:
        # Clear destination
        dest.execute(
            """
            TRUNCATE TABLE
                reminders,
                recurring_expenses,
                budgets,
                expenses,
                user_settings,
                users
            RESTART IDENTITY CASCADE
            """
        ).close()

        for table in table_order:
            rows = source.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                continue

            columns = list(rows[0].keys())
            columns_sql = ", ".join(columns)
            placeholders = ", ".join(["%s"] * len(columns))
            update_columns = [c for c in columns if c != "id"]
            update_assignments = ", ".join(
                f"{c} = EXCLUDED.{c}" for c in update_columns
            )
            query = (
                f"INSERT INTO {table} ({columns_sql}) VALUES ({placeholders}) "
                f"ON CONFLICT (id) DO UPDATE SET {update_assignments}"
            )

            boolean_cols = {"is_verified", "is_recurring", "active"}
            for row in rows:
                values = []
                for col in columns:
                    val = row[col]
                    if col in boolean_cols and val is not None:
                        val = bool(val)
                    values.append(val)
                dest.execute(query, tuple(values)).close()

        # Resequence all serial columns so next INSERT gets a correct id
        for table in table_order:
            dest.execute(
                f"""
                SELECT setval(
                    pg_get_serial_sequence('{table}', 'id'),
                    COALESCE((SELECT MAX(id) FROM {table}), 1),
                    (SELECT MAX(id) FROM {table}) IS NOT NULL
                )
                """
            ).close()

        dest.commit()

    source.close()
