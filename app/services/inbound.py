import logging
from enum import StrEnum

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core.config import Settings
from app.models import ProcessedMessage
from app.schemas.kapso_webhook import MessageReceived
from app.services import billing
from app.services.messaging import KapsoError, Messenger

logger = logging.getLogger(__name__)


class InboundOutcome(StrEnum):
    PROCESSED = "processed"
    DUPLICATE = "duplicate"
    UNDELIVERABLE = "undeliverable"
    RETRY = "retry"


def handle_message_received(
    session: Session, messenger: Messenger, settings: Settings, event: MessageReceived
) -> InboundOutcome:
    """Process one inbound message exactly once, even when Kapso redelivers it."""
    message_id = event.message.id

    # Claim the message ID and do the work in one transaction: a transient send failure
    # rolls the claim back so Kapso's retry processes it; a duplicate hits the primary key.
    session.add(ProcessedMessage(message_id=message_id))
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        return InboundOutcome.DUPLICATE

    try:
        billing.reply_to_customer(
            session, messenger, settings, event.conversation.phone_number, event.message.selection_id
        )
    except KapsoError as exc:
        if not exc.retryable:
            # Keep the claim so redeliveries are no-ops; a retry would fail the same way.
            session.commit()
            logger.warning("Giving up on %s: %s", message_id, exc)
            return InboundOutcome.UNDELIVERABLE
        session.rollback()
        logger.exception("Failed to reply to %s", message_id)
        return InboundOutcome.RETRY

    session.commit()
    return InboundOutcome.PROCESSED
