"""Apply database migrations. Equivalent to `alembic upgrade head`."""
from database import upgrade_schema

if __name__ == "__main__":
    upgrade_schema()
    print("Database schema is up to date")
