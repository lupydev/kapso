from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.api.deps import SessionDep, require_admin
from app.api.templates import templates
from app.services import billing, events

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("", response_class=HTMLResponse)
def admin_page(request: Request, session: SessionDep):
    invoices = billing.all_invoices(session)
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "invoices": [(invoice, billing.invoice_amount(invoice)) for invoice in invoices],
            "webhooks": events.recent_webhooks(session),
        },
    )
