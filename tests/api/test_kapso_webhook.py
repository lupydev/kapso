import hashlib
import hmac

import pytest
from sqlmodel import Session, select

from app.models import Invoice, PaymentLink
from tests.support import CUSTOMER, SECRET, inbound, post_event


def test_rejects_invalid_signature(client, kapso):
    response = post_event(client, inbound("wamid.1"), secret="wrong")

    assert response.status_code == 401
    assert kapso.sent == []


@pytest.mark.parametrize("signature", ["", "ñ" * 64, "not-hex", "A" * 64])
def test_malformed_signatures_are_rejected(client, kapso, signature):
    response = client.post(
        "/webhooks/kapso",
        content=b"{}",
        headers={"X-Webhook-Event": "whatsapp.message.received", "X-Webhook-Signature": signature.encode()},
    )

    assert response.status_code == 401
    assert kapso.sent == []


def test_ignores_other_events(client, kapso):
    response = post_event(client, inbound("wamid.1"), event="whatsapp.message.delivered")

    assert response.status_code == 200
    assert kapso.sent == []


def test_unparseable_signed_payload_is_acknowledged(client, kapso):
    raw = b"not json"
    signature = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    response = client.post(
        "/webhooks/kapso",
        content=raw,
        headers={"X-Webhook-Event": "whatsapp.message.received", "X-Webhook-Signature": signature},
    )

    assert response.status_code == 400
    assert kapso.sent == []


def test_text_message_replies_with_invoice_buttons(client, kapso, engine):
    response = post_event(client, inbound("wamid.1", text="hola"))

    assert response.status_code == 200
    assert len(kapso.sent) == 1
    reply = kapso.sent[0]
    assert reply["to"] == CUSTOMER
    assert reply["kind"] == "buttons"
    assert "50,000.00 COP" in reply["body"]
    assert [button_id for button_id, _ in reply["buttons"]] == ["pay", "paid"]
    with Session(engine) as session:
        invoices = session.exec(select(Invoice)).all()
    assert len(invoices) == 1
    assert invoices[0].status == "pending"


def test_duplicate_delivery_is_processed_once(client, kapso, engine):
    first = post_event(client, inbound("wamid.1", text="hola"))
    second = post_event(client, inbound("wamid.1", text="hola"))

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(kapso.sent) == 1
    with Session(engine) as session:
        assert len(session.exec(select(Invoice)).all()) == 1


def test_pay_button_returns_the_same_link_every_time(client, kapso, engine):
    post_event(client, inbound("wamid.1", text="hola"))
    post_event(client, inbound("wamid.2", button="pay"))
    post_event(client, inbound("wamid.3", button="pay"))

    links = [m["body"] for m in kapso.sent[1:]]
    assert len(links) == 2
    assert links[0] == links[1]
    assert "https://example.test/pay/" in links[0]
    with Session(engine) as session:
        assert len(session.exec(select(PaymentLink)).all()) == 1


def test_paid_button_before_paying_reports_pending(client, kapso):
    post_event(client, inbound("wamid.1", text="hola"))
    post_event(client, inbound("wamid.2", button="paid"))

    assert "not received" in kapso.sent[-1]["body"]


def test_failed_send_returns_500_so_kapso_retries(client, kapso):
    kapso.fail_next = True
    failed = post_event(client, inbound("wamid.1", text="hola"))
    retried = post_event(client, inbound("wamid.1", text="hola"))

    assert failed.status_code == 500
    assert retried.status_code == 200
    assert len(kapso.sent) == 1


def test_permanent_send_failure_is_acknowledged_without_retry(client, kapso):
    # e.g. Kapso 403 for a recipient the sandbox can't reach: retrying can't succeed.
    kapso.fail_next = True
    kapso.fail_retryable = False
    first = post_event(client, inbound("wamid.1", text="hola"))
    redelivery = post_event(client, inbound("wamid.1", text="hola"))

    assert first.status_code == 200
    assert first.json() == {"status": "undeliverable"}
    assert redelivery.json() == {"status": "duplicate"}
    assert kapso.sent == []


def test_message_without_id_is_rejected_as_malformed(client, kapso):
    payload = inbound("wamid.1", text="hola")
    del payload["message"]["id"]

    response = post_event(client, payload)

    assert response.status_code == 400
    assert kapso.sent == []
