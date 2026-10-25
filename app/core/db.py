from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import get_settings


def engine_options(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        # FastAPI runs sync handlers in a threadpool; SQLite connections must allow that.
        return {"connect_args": {"check_same_thread": False}}
    # Drop connections the managed database closed while idle.
    return {"pool_pre_ping": True}


@lru_cache
def get_engine() -> Engine:
    # Import the tables so create_all sees them.
    import app.models  # noqa: F401

    database_url = get_settings().database_url
    engine = create_engine(database_url, **engine_options(database_url))
    SQLModel.metadata.create_all(engine)
    return engine


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
