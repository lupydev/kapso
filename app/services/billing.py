from datetime import UTC, datetime

from sqlmodel import Session, select, update

from app.core.config import Settings
from app.models import Invoice, InvoiceStatus, PaymentLink
from app.services.messaging import Messenger
from app.utils.money import format_amount

PAY = "pay"
PAID = "paid"


def invoice_amount(invoice: Invoice) -> str:
    return format_amount(invoice.amount_cents, invoice.currency)


def current_invoice(session: Session, phone_number: str, settings: Settings) -> Invoice:
    """Return the customer's latest invoice, creating a pending one on first contact."""
    invoice = session.exec(
        select(Invoice).where(Invoice.phone_number == phone_number).order_by(Invoice.id.desc())
    ).first()
    if invoice is None:
        invoice = Invoice(
            phone_number=phone_number,
            amount_cents=settings.invoice_amount_cents,
            currency=settings.invoice_currency,
        )
        session.add(invoice)
        session.flush()
    return invoice


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


def reply_to_customer(
    session: Session, messenger: Messenger, settings: Settings, phone_number: str, button_id: str | None
) -> None:
    """Answer an inbound message based on the invoice state and the button tapped."""
    invoice = current_invoice(session, phone_number, settings)

    if invoice.status == InvoiceStatus.PAID:
        messenger.send_text(phone_number, f"Your invoice for {invoice_amount(invoice)} is already paid. Thank you!")
    elif button_id == PAY:
        link = get_or_create_payment_link(session, invoice)
        messenger.send_text(
            phone_number,
            f"Pay {invoice_amount(invoice)} here: {settings.public_base_url}/pay/{link.token}",
        )
    elif button_id == PAID:
        messenger.send_text(
            phone_number,
            "We have not received your payment yet. Tap Pay to get your payment link.",
        )
    else:
        messenger.send_buttons(
            phone_number,
            f"Hi! You have a pending invoice for {invoice_amount(invoice)}.",
            [(PAY, "Pay"), (PAID, "I already paid")],
        )


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
    messenger.send_text(invoice.phone_number, f"Payment received: {invoice_amount(invoice)}. Thank you!")
