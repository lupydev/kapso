from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class ProcessedMessage(SQLModel, table=True):
    """Inbound WhatsApp message IDs already handled; the primary key makes retries no-ops."""

    message_id: str = Field(primary_key=True)
    processed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
