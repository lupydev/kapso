from datetime import UTC, datetime

from sqlmodel import Session, select, update

from app.config import Settings
from app.db import Invoice, PaymentLink
from app.kapso import Messenger

PAY = "pay"
PAID = "paid"


def format_amount(invoice: Invoice) -> str:
    return f"{invoice.amount_cents / 100:,.2f} {invoice.currency}"


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


def payment_link(session: Session, invoice: Invoice) -> PaymentLink:
    link = session.exec(select(PaymentLink).where(PaymentLink.invoice_id == invoice.id)).first()
    if link is None:
        link = PaymentLink(invoice_id=invoice.id)
        session.add(link)
        session.flush()
    return link


def handle_message(
    session: Session, messenger: Messenger, settings: Settings, phone_number: str, button_id: str | None
) -> None:
    invoice = current_invoice(session, phone_number, settings)

    if invoice.status == "paid":
        messenger.send_text(phone_number, f"Your invoice for {format_amount(invoice)} is already paid. Thank you!")
    elif button_id == PAY:
        link = payment_link(session, invoice)
        messenger.send_text(
            phone_number,
            f"Pay {format_amount(invoice)} here: {settings.public_base_url}/pay/{link.token}",
        )
    elif button_id == PAID:
        messenger.send_text(
            phone_number,
            "We have not received your payment yet. Tap Pay to get your payment link.",
        )
    else:
        messenger.send_buttons(
            phone_number,
            f"Hi! You have a pending invoice for {format_amount(invoice)}.",
            [(PAY, "Pay"), (PAID, "I already paid")],
        )


def current_invoice_for_link(session: Session, link: PaymentLink) -> Invoice:
    return session.get(Invoice, link.invoice_id)


def mark_paid(session: Session, link: PaymentLink) -> tuple[Invoice, bool]:
    """Mark the invoice paid. Returns whether this call was the one that paid it."""
    # Conditional update instead of read-then-write: under concurrent confirms (double
    # click) only one UPDATE matches a pending row, so only that request sends a receipt.
    result = session.exec(
        update(Invoice)
        .where(Invoice.id == link.invoice_id, Invoice.status != "paid")
        .values(status="paid", paid_at=datetime.now(UTC))
    )
    invoice = session.get(Invoice, link.invoice_id, populate_existing=True)
    return invoice, result.rowcount == 1


def send_receipt(messenger: Messenger, invoice: Invoice) -> None:
    messenger.send_text(invoice.phone_number, f"Payment received: {format_amount(invoice)}. Thank you!")
