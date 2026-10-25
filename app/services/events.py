import logging

from sqlmodel import Session, select

from app.models import WebhookEvent

logger = logging.getLogger(__name__)

MAX_PAYLOAD_CHARS = 10_000


def record_webhook(
    session: Session,
    *,
    body: bytes,
    event_type: str | None,
    outcome: str,
    status_code: int,
    message_id: str | None = None,
    phone_number: str | None = None,
) -> None:
    """Store a verified webhook request. Payloads hold customer data; keep the admin page private."""
    session.add(
        WebhookEvent(
            event_type=event_type,
            message_id=message_id,
            phone_number=phone_number,
            outcome=outcome,
            status_code=status_code,
            payload=body.decode("utf-8", errors="replace")[:MAX_PAYLOAD_CHARS],
        )
    )
    session.commit()


def recent_webhooks(session: Session, limit: int = 50) -> list[WebhookEvent]:
    return list(session.exec(select(WebhookEvent).order_by(WebhookEvent.id.desc()).limit(limit)).all())
