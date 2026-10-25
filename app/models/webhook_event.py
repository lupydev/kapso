from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class WebhookEvent(SQLModel, table=True):
    """One signature-verified webhook request and what the app did with it."""

    id: int | None = Field(default=None, primary_key=True)
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    event_type: str | None = None
    message_id: str | None = Field(default=None, index=True)
    phone_number: str | None = None
    outcome: str
    status_code: int
    payload: str
