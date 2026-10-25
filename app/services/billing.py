import logging
from datetime import UTC, datetime

from sqlmodel import Session, select, update

from app.core.config import Settings
from app.models import Invoice, InvoiceStatus, PaymentLink
from app.services.messaging import KapsoError, Messenger
from app.utils.money import format_amount
from app.utils.phone import normalize_phone

logger = logging.getLogger(__name__)

INVOICE_ROW_PREFIX = "invoice:"
MAX_LIST_ROWS = 10  # WhatsApp list messages allow at most 10 rows.
LIST_BUTTON = "View invoices"


def invoice_amount(invoice: Invoice) -> str:
    return format_amount(invoice.amount_cents, invoice.currency)


def create_invoice(
    session: Session, phone_number: str, amount_cents: int, currency: str, description: str
) -> Invoice:
    invoice = Invoice(
        phone_number=normalize_phone(phone_number),
        amount_cents=amount_cents,
        currency=currency,
        description=description,
    )
    session.add(invoice)
    session.flush()
    return invoice


def pending_invoices(session: Session, phone_number: str) -> list[Invoice]:
    return list(
        session.exec(
            select(Invoice)
            .where(Invoice.phone_number == normalize_phone(phone_number), Invoice.status == InvoiceStatus.PENDING)
            .order_by(Invoice.id)
        ).all()
    )


def get_or_create_payment_link(session: Session, invoice: Invoice) -> PaymentLink:
    link = session.exec(select(PaymentLink).where(PaymentLink.invoice_id == invoice.id)).first()
    if link is None:
        link = PaymentLink(invoice_id=invoice.id)
        session.add(link)
        session.flush()
    return link


def find_payment_link(session: Session, token: str) -> PaymentLink | None:
    return session.exec(select(PaymentLink).where(PaymentLink.token == token)).first()


def invoice_for_link(session: Session, link: PaymentLink) -> Invoice:
    return session.get(Invoice, link.invoice_id)


def _chosen_invoice(session: Session, phone_number: str, row_id: str) -> Invoice | None:
    """The invoice behind a list row, only if it belongs to this customer and is still pending."""
    invoice_id = row_id.removeprefix(INVOICE_ROW_PREFIX)
    if not invoice_id.isdigit():
        return None
    invoice = session.get(Invoice, int(invoice_id))
    if invoice is None or invoice.phone_number != normalize_phone(phone_number):
        return None
    return invoice if invoice.status == InvoiceStatus.PENDING else None


def _send_invoice_list(messenger: Messenger, phone_number: str, invoices: list[Invoice], intro: str = "") -> None:
    if not invoices:
        messenger.send_text(phone_number, f"{intro}You have no pending invoices. Thank you!")
        return
    shown = invoices[:MAX_LIST_ROWS]
    if len(invoices) > len(shown):
        summary = f"You have {len(invoices)} pending invoices (showing {len(shown)} of {len(invoices)})."
    else:
        summary = f"You have {len(invoices)} pending invoice{'s' if len(invoices) > 1 else ''}."
    rows = [
        (f"{INVOICE_ROW_PREFIX}{invoice.id}", invoice_amount(invoice)[:24], f"#{invoice.id} {invoice.description}"[:72])
        for invoice in shown
    ]
    messenger.send_list(phone_number, f"{intro}{summary} Pick one to pay.", LIST_BUTTON, rows)


def reply_to_customer(
    session: Session, messenger: Messenger, settings: Settings, phone_number: str, selection_id: str | None
) -> None:
    """Answer an inbound message: a chosen invoice gets its payment link, anything else the invoice list."""
    if selection_id and selection_id.startswith(INVOICE_ROW_PREFIX):
        invoice = _chosen_invoice(session, phone_number, selection_id)
        if invoice is not None:
            link = get_or_create_payment_link(session, invoice)
            messenger.send_text(
                phone_number,
                f"Pay {invoice_amount(invoice)} for {invoice.description}: {settings.public_base_url}/pay/{link.token}",
            )
            return
        _send_invoice_list(
            messenger, phone_number, pending_invoices(session, phone_number), "That invoice isn't available anymore. "
        )
        return

    _send_invoice_list(messenger, phone_number, pending_invoices(session, phone_number))


def mark_paid(session: Session, link: PaymentLink) -> tuple[Invoice, bool]:
    """Mark the invoice paid. Returns whether this call was the one that paid it."""
    # Conditional update instead of read-then-write: under concurrent confirms (double
    # click) only one UPDATE matches a pending row, so only that request sends a receipt.
    result = session.exec(
        update(Invoice)
        .where(Invoice.id == link.invoice_id, Invoice.status != InvoiceStatus.PAID)
        .values(status=InvoiceStatus.PAID, paid_at=datetime.now(UTC))
    )
    invoice = session.get(Invoice, link.invoice_id, populate_existing=True)
    return invoice, result.rowcount == 1


def send_receipt(messenger: Messenger, invoice: Invoice) -> None:
    messenger.send_text(
        invoice.phone_number, f"Payment received: {invoice_amount(invoice)} for {invoice.description}. Thank you!"
    )


def confirm_payment(session: Session, messenger: Messenger, link: PaymentLink) -> Invoice:
    """Record the payment, then notify the customer once."""
    invoice, newly_paid = mark_paid(session, link)
    # Commit before notifying: the payment is the source of truth, the receipt is
    # best-effort (Kapso rejects free-form text outside the 24-hour window).
    session.commit()
    if newly_paid:
        try:
            send_receipt(messenger, invoice)
        except KapsoError:
            logger.exception("Payment recorded but receipt failed for link %s", link.id)
    return invoice
