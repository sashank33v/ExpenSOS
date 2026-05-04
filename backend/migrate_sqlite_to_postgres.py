import os

from database import SQLITE_DB_PATH, migrate_sqlite_to_postgres


if __name__ == "__main__":
    sqlite_path = os.environ.get("SQLITE_DB_PATH", SQLITE_DB_PATH)
    migrate_sqlite_to_postgres(sqlite_path)
    print(f"Migrated SQLite data from {sqlite_path} into PostgreSQL.")
