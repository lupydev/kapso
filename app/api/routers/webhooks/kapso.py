import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.api.deps import MessengerDep, SessionDep, SettingsDep
from app.core.security import valid_webhook_signature
from app.schemas.kapso_webhook import MESSAGE_RECEIVED, MessageReceived
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
        return {"status": "ignored"}

    try:
        event = MessageReceived.model_validate_json(body)
    except ValidationError:
        # Signed but unusable: retrying won't fix it, so answer 4xx instead of 500.
        logger.warning("Ignoring malformed webhook payload")
        raise HTTPException(status_code=400, detail="malformed payload")

    outcome = handle_message_received(session, messenger, settings, event)
    if outcome == InboundOutcome.RETRY:
        # Non-200 makes Kapso redeliver the same message.
        return JSONResponse({"status": outcome}, status_code=500)
    return {"status": outcome}
