import pytest

from app.core.config import Settings
from app.core.db import engine_options


def _settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        kapso_api_key="k",
        kapso_phone_number_id="1",
        kapso_webhook_secret="s",
        public_base_url="https://x",
        database_url=database_url,
    )


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgres://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        ("postgresql://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("sqlite:///db.sqlite3", "sqlite:///db.sqlite3"),
    ],
)
def test_database_url_uses_the_installed_postgres_driver(given, expected):
    # Railway hands out postgres:// / postgresql:// URLs; SQLAlchemy needs the psycopg (v3) dialect.
    assert _settings(given).database_url == expected


def test_sqlite_only_options_are_not_passed_to_postgres():
    assert engine_options("sqlite:///db.sqlite3") == {"connect_args": {"check_same_thread": False}}
    assert engine_options("postgresql+psycopg://u:p@host/db") == {"pool_pre_ping": True}
