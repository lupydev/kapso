import hashlib
import hmac
import json
import logging
import re
from html import escape
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app import billing
from app.config import Settings, get_settings
from app.db import PaymentLink, ProcessedMessage, get_session
from app.kapso import KapsoError, Messenger, get_kapso

logger = logging.getLogger(__name__)

app = FastAPI(title="Kapso payment collection")

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
KapsoDep = Annotated[Messenger, Depends(get_kapso)]


SIGNATURE_FORMAT = re.compile(r"[0-9a-f]{64}")


def _valid_signature(secret: str, body: bytes, signature: str | None) -> bool:
    # Check the shape first: compare_digest raises on non-ASCII input.
    if not signature or not SIGNATURE_FORMAT.fullmatch(signature):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _button_id(message: dict) -> str | None:
    interactive = message.get("interactive") or {}
    return (interactive.get("button_reply") or {}).get("id")


async def raw_body(request: Request) -> bytes:
    return await request.body()


# Sync handler on purpose: DB and Kapso calls are blocking, so FastAPI runs it in a threadpool.
@app.post("/webhooks/kapso")
def kapso_webhook(
    body: Annotated[bytes, Depends(raw_body)],
    session: SessionDep,
    settings: SettingsDep,
    kapso: KapsoDep,
    x_webhook_event: Annotated[str | None, Header()] = None,
    x_webhook_signature: Annotated[str | None, Header()] = None,
):
    if not _valid_signature(settings.kapso_webhook_secret, body, x_webhook_signature):
        raise HTTPException(status_code=401, detail="invalid signature")
    if x_webhook_event != "whatsapp.message.received":
        return {"status": "ignored"}

    try:
        event = json.loads(body)
        message = event["message"]
        phone_number = event["conversation"]["phone_number"]
    except (ValueError, KeyError, TypeError):
        # Signed but unusable: retrying won't fix it, so answer 4xx instead of 500.
        logger.warning("Ignoring malformed webhook payload")
        raise HTTPException(status_code=400, detail="malformed payload")

    # Claim the message ID and do the work in one transaction: a failed send rolls the
    # claim back and returns 500, so Kapso's retry processes it; a duplicate hits the key.
    session.add(ProcessedMessage(message_id=message["id"]))
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        return {"status": "duplicate"}

    try:
        billing.handle_message(session, kapso, settings, phone_number, _button_id(message))
    except KapsoError as exc:
        if not exc.retryable:
            # Keep the claim so redeliveries are no-ops; a retry would fail the same way.
            session.commit()
            logger.warning("Giving up on %s: %s", message["id"], exc)
            return {"status": "undeliverable"}
        session.rollback()
        logger.exception("Failed to reply to %s", message["id"])
        return JSONResponse({"status": "retry"}, status_code=500)

    session.commit()
    return {"status": "processed"}


def _get_link(session: Session, token: str) -> PaymentLink:
    link = session.exec(select(PaymentLink).where(PaymentLink.token == token)).first()
    if link is None:
        raise HTTPException(status_code=404, detail="payment link not found")
    return link


@app.get("/pay/{token}", response_class=HTMLResponse)
def checkout(token: str, session: SessionDep):
    link = _get_link(session, token)
    invoice = billing.current_invoice_for_link(session, link)
    amount = escape(billing.format_amount(invoice))
    if invoice.status == "paid":
        action = "<p>This invoice is already paid.</p>"
    else:
        action = (
            f'<form method="post" action="/pay/{escape(token)}/confirm">'
            "<button>Simulate successful payment</button></form>"
        )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Simulated checkout</title></head>
<body style="font-family: system-ui; max-width: 28rem; margin: 3rem auto; padding: 0 1rem">
<h1>Simulated checkout</h1><p>Amount due: <strong>{amount}</strong></p>{action}
<p><small>Demo only. No real money moves.</small></p></body></html>"""


@app.post("/pay/{token}/confirm", response_class=HTMLResponse)
def confirm(token: str, session: SessionDep, kapso: KapsoDep):
    link = _get_link(session, token)
    invoice, newly_paid = billing.mark_paid(session, link)
    # Commit before notifying: the payment is the source of truth, the receipt is
    # best-effort (Kapso rejects free-form text outside the 24-hour window).
    session.commit()
    if newly_paid:
        try:
            billing.send_receipt(kapso, invoice)
        except KapsoError:
            logger.exception("Payment recorded but receipt failed for link %s", link.id)
    return f"<p>Paid {escape(billing.format_amount(invoice))}. You can return to WhatsApp.</p>"
