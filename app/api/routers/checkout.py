import logging
from html import escape

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.api.deps import MessengerDep, SessionDep
from app.models import InvoiceStatus, PaymentLink
from app.services import billing
from app.services.messaging import KapsoError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pay", tags=["checkout"])


def _get_link(session: Session, token: str) -> PaymentLink:
    link = billing.find_payment_link(session, token)
    if link is None:
        raise HTTPException(status_code=404, detail="payment link not found")
    return link


@router.get("/{token}", response_class=HTMLResponse)
def checkout_page(token: str, session: SessionDep):
    invoice = billing.invoice_for_link(session, _get_link(session, token))
    amount = escape(billing.invoice_amount(invoice))
    if invoice.status == InvoiceStatus.PAID:
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


@router.post("/{token}/confirm", response_class=HTMLResponse)
def confirm_payment(token: str, session: SessionDep, messenger: MessengerDep):
    link = _get_link(session, token)
    invoice, newly_paid = billing.mark_paid(session, link)
    # Commit before notifying: the payment is the source of truth, the receipt is
    # best-effort (Kapso rejects free-form text outside the 24-hour window).
    session.commit()
    if newly_paid:
        try:
            billing.send_receipt(messenger, invoice)
        except KapsoError:
            logger.exception("Payment recorded but receipt failed for link %s", link.id)
    return f"<p>Paid {escape(billing.invoice_amount(invoice))}. You can return to WhatsApp.</p>"
