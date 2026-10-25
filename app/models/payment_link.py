import secrets
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class PaymentLink(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    # unique: one link per invoice, so repeated "pay" taps return the same URL.
    invoice_id: int = Field(foreign_key="invoice.id", unique=True)
    token: str = Field(default_factory=lambda: secrets.token_urlsafe(16), unique=True, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
