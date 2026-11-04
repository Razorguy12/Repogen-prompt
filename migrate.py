"""Run the application's idempotent schema migrations."""
from database import Base, engine, run_migrations

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    print("Database schema is up to date")
