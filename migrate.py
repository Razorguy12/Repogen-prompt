"""Apply database migrations. Equivalent to `alembic upgrade head`.

If DATABASE_URL is not visible here (e.g. production keeps it in the systemd
EnvironmentFile rather than .env), skip instead of migrating the SQLite
fallback. The app applies the same migrations at startup, with its real
environment, under a Postgres advisory lock.
"""
import os
import sys

from dotenv import load_dotenv

if __name__ == "__main__":
    load_dotenv()
    if not os.getenv("DATABASE_URL"):
        print("migrate.py: DATABASE_URL not set here; skipping. Migrations will run when the service starts.")
        sys.exit(0)
    from database import upgrade_schema
    upgrade_schema()
    print("Database schema is up to date")
