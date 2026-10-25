from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.api.deps import MessengerDep, SessionDep
from app.api.templates import templates
from app.models import InvoiceStatus, PaymentLink
from app.services import billing

router = APIRouter(prefix="/pay", tags=["checkout"])


def _get_link(session: Session, token: str) -> PaymentLink:
    link = billing.find_payment_link(session, token)
    if link is None:
        raise HTTPException(status_code=404, detail="payment link not found")
    return link


@router.get("/{token}", response_class=HTMLResponse)
def checkout_page(request: Request, token: str, session: SessionDep):
    invoice = billing.invoice_for_link(session, _get_link(session, token))
    return templates.TemplateResponse(
        request,
        "checkout.html",
        {
            "invoice": invoice,
            "amount": billing.invoice_amount(invoice),
            "paid": invoice.status == InvoiceStatus.PAID,
            "token": token,
        },
    )


@router.post("/{token}/confirm", response_class=HTMLResponse)
def confirm_payment(request: Request, token: str, session: SessionDep, messenger: MessengerDep):
    invoice = billing.confirm_payment(session, messenger, _get_link(session, token))
    return templates.TemplateResponse(request, "paid.html", {"amount": billing.invoice_amount(invoice)})
