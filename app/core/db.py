from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    # Import the tables so create_all sees them.
    import app.models  # noqa: F401

    engine = create_engine(get_settings().database_url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
