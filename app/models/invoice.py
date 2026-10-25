from datetime import UTC, datetime
from enum import StrEnum

from sqlmodel import Field, SQLModel


class InvoiceStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"


class Invoice(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    phone_number: str = Field(index=True)
    amount_cents: int
    currency: str
    status: str = InvoiceStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    paid_at: datetime | None = None
