from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Invoice, PaymentLink
from app.services import billing
from tests.support import CUSTOMER


def test_concurrent_confirms_pay_only_once(tmp_path):
    # File-backed DB so each session has its own connection, like two real requests.
    engine = create_engine(f"sqlite:///{tmp_path / 'race.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        invoice = Invoice(phone_number=CUSTOMER, amount_cents=100, currency="COP")
        session.add(invoice)
        session.flush()
        session.add(PaymentLink(invoice_id=invoice.id))
        session.commit()

    # Both requests read the invoice as pending before either commits (double click).
    with Session(engine) as first, Session(engine) as second:
        link = first.exec(select(PaymentLink)).one()
        # Keep references: the sessions' identity maps hold these stale reads.
        seen_by_first = first.get(Invoice, link.invoice_id)
        seen_by_second = second.get(Invoice, link.invoice_id)
        assert seen_by_first.status == seen_by_second.status == "pending"
        _, first_paid = billing.mark_paid(first, link)
        first.commit()
        _, second_paid = billing.mark_paid(second, link)
        second.commit()

    assert (first_paid, second_paid) == (True, False)
