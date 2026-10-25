from datetime import UTC, datetime
from enum import StrEnum

from sqlmodel import AutoString, Field, SQLModel


class InvoiceStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"


class Invoice(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    phone_number: str = Field(index=True)
    amount_cents: int
    currency: str
    description: str = ""
    # Stored as plain text ('pending'/'paid'), not a SQL enum, so existing rows stay readable.
    status: InvoiceStatus = Field(default=InvoiceStatus.PENDING, sa_type=AutoString)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    paid_at: datetime | None = None
