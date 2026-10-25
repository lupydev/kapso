from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.api.deps import SessionDep, require_admin
from app.api.templates import templates
from app.models import InvoiceStatus
from app.services import billing, events

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("", response_class=HTMLResponse)
def admin_page(request: Request, session: SessionDep):
    invoices = billing.all_invoices(session)
    webhooks = events.recent_webhooks(session)
    paid = [invoice for invoice in invoices if invoice.status == InvoiceStatus.PAID]
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "invoices": [(invoice, billing.invoice_amount(invoice)) for invoice in invoices],
            "webhooks": [(event, events.pretty_payload(event.payload)) for event in webhooks],
            "summary": {
                "pending": len(invoices) - len(paid),
                "paid": len(paid),
                "events": len(webhooks),
                "failed": sum(1 for event in webhooks if event.status_code >= 400),
            },
        },
    )
