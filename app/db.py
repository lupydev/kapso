import secrets
from collections.abc import Iterator
from datetime import UTC, datetime
from functools import lru_cache

from sqlalchemy import Engine
from sqlmodel import Field, Session, SQLModel, create_engine

from app.config import get_settings


def _now() -> datetime:
    return datetime.now(UTC)


class ProcessedMessage(SQLModel, table=True):
    """Inbound WhatsApp message IDs already handled; the primary key makes retries no-ops."""

    message_id: str = Field(primary_key=True)
    processed_at: datetime = Field(default_factory=_now)


class Invoice(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    phone_number: str = Field(index=True)
    amount_cents: int
    currency: str
    status: str = "pending"
    created_at: datetime = Field(default_factory=_now)
    paid_at: datetime | None = None


class PaymentLink(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    # unique: one link per invoice, so repeated "pay" taps return the same URL.
    invoice_id: int = Field(foreign_key="invoice.id", unique=True)
    token: str = Field(default_factory=lambda: secrets.token_urlsafe(16), unique=True, index=True)
    created_at: datetime = Field(default_factory=_now)


@lru_cache
def get_engine() -> Engine:
    engine = create_engine(get_settings().database_url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
