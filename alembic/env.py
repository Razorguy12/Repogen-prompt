"""Alembic environment. Uses the app's engine so dev (SQLite) and prod (Postgres) match."""
from logging.config import fileConfig

from alembic import context

from database import Base, engine

config = context.config
if config.config_file_name is not None and not config.attributes.get("connection"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


# Objects managed only in migrations (dialect-specific), ignored by autogenerate.
MIGRATION_ONLY = {"ix_patients_full_name_trgm"}


def _include_object(obj, name, type_, reflected, compare_to):
    return name not in MIGRATION_ONLY


def _run(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    shared = config.attributes.get("connection")
    if shared is not None:
        _run(shared)
        return
    with engine.connect() as connection:
        _run(connection)


if context.is_offline_mode():
    context.configure(url=str(engine.url), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    run_migrations_online()
