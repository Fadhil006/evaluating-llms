from alembic import context
from app import models  # noqa: F401 - load metadata for autogenerate
from app.config import load_settings
from app.db import Base, make_engine

config = context.config
target_metadata = Base.metadata


def run_migrations_online():
    engine = make_engine(load_settings())
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


run_migrations_online()
