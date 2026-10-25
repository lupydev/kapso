from sqlmodel import Session, select

from app.models import Invoice, PaymentLink
from tests.support import inbound, post_event


def test_checkout_confirmation_marks_invoice_paid_once(client, kapso, engine, seed):
    (invoice_id,) = seed((5000000, "Rent - October"))
    post_event(client, inbound("wamid.2", row=f"invoice:{invoice_id}"))
    with Session(engine) as session:
        token = session.exec(select(PaymentLink)).one().token

    page = client.get(f"/pay/{token}")
    first = client.post(f"/pay/{token}/confirm")
    second = client.post(f"/pay/{token}/confirm")

    assert page.status_code == 200
    assert "50,000.00 COP" in page.text
    assert "Rent - October" in page.text
    assert first.status_code == 200
    assert second.status_code == 200
    receipts = [m for m in kapso.sent if "Payment received" in m["body"]]
    assert len(receipts) == 1
    with Session(engine) as session:
        assert session.exec(select(Invoice)).one().status == "paid"

    assert "Rent - October" in receipts[0]["body"]
    post_event(client, inbound("wamid.3", text="hola"))
    assert "no pending invoices" in kapso.sent[-1]["body"]


def test_unknown_payment_link_returns_404(client):
    assert client.get("/pay/nope").status_code == 404
    assert client.post("/pay/nope/confirm").status_code == 404


def test_payment_is_recorded_even_if_receipt_cannot_be_sent(client, kapso, engine, seed):
    # Outside the 24-hour window Kapso rejects free-form text; the payment must still stick.
    (invoice_id,) = seed((5000000, "Rent - October"))
    post_event(client, inbound("wamid.2", row=f"invoice:{invoice_id}"))
    with Session(engine) as session:
        token = session.exec(select(PaymentLink)).one().token

    kapso.fail_next = True
    response = client.post(f"/pay/{token}/confirm")

    assert response.status_code == 200
    with Session(engine) as session:
        assert session.exec(select(Invoice)).one().status == "paid"
    assert not [m for m in kapso.sent if "Payment received" in m["body"]]


def test_checkout_page_escapes_invoice_description(client, seed, engine):
    (invoice_id,) = seed((100, "<script>alert(1)</script>"))
    post_event(client, inbound("wamid.1", row=f"invoice:{invoice_id}"))
    with Session(engine) as session:
        token = session.exec(select(PaymentLink)).one().token

    page = client.get(f"/pay/{token}")

    assert "<script>" not in page.text
    assert "&lt;script&gt;" in page.text
