import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.deps import MessengerDep, SessionDep, SettingsDep
from app.core.security import valid_webhook_signature
from app.schemas.kapso_webhook import MESSAGE_RECEIVED, MessageReceived
from app.services import events
from app.services.inbound import InboundOutcome, handle_message_received

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


async def raw_body(request: Request) -> bytes:
    return await request.body()


def verified_body(
    body: Annotated[bytes, Depends(raw_body)],
    settings: SettingsDep,
    x_webhook_signature: Annotated[str | None, Header()] = None,
) -> bytes:
    """Reject the request unless it carries Kapso's signature for the exact raw body."""
    if not valid_webhook_signature(settings.kapso_webhook_secret, body, x_webhook_signature):
        raise HTTPException(status_code=401, detail="invalid signature")
    return body


def _log_webhook(session, body: bytes, event_type: str | None, outcome: str, status_code: int, event=None) -> None:
    # The log is for humans; never let it change what Kapso sees (a 500 would cause a retry).
    try:
        events.record_webhook(
            session,
            body=body,
            event_type=event_type,
            outcome=outcome,
            status_code=status_code,
            message_id=event.message.id if event else None,
            phone_number=event.conversation.phone_number if event else None,
        )
    except Exception:
        session.rollback()
        logger.exception("Could not log webhook event")


# Sync handler on purpose: DB and Kapso calls are blocking, so FastAPI runs it in a threadpool.
@router.post("/kapso")
def kapso_webhook(
    body: Annotated[bytes, Depends(verified_body)],
    session: SessionDep,
    settings: SettingsDep,
    messenger: MessengerDep,
    x_webhook_event: Annotated[str | None, Header()] = None,
):
    if x_webhook_event != MESSAGE_RECEIVED:
        _log_webhook(session, body, x_webhook_event, "ignored", 200)
        return {"status": "ignored"}

    try:
        # json.loads detects UTF-8 BOM and UTF-16 bodies; model_validate_json does not.
        event = MessageReceived.model_validate(json.loads(body))
    except ValueError:  # JSONDecodeError, UnicodeDecodeError and ValidationError
        # Signed but unusable: retrying won't fix it, so answer 4xx instead of 500.
        logger.warning("Ignoring malformed webhook payload")
        _log_webhook(session, body, x_webhook_event, "malformed", 400)
        return JSONResponse({"detail": "malformed payload"}, status_code=400)

    outcome = handle_message_received(session, messenger, settings, event)
    # Non-200 makes Kapso redeliver the same message.
    status_code = 500 if outcome == InboundOutcome.RETRY else 200
    _log_webhook(session, body, x_webhook_event, outcome, status_code, event)
    return JSONResponse({"status": outcome}, status_code=status_code)
