import json

import pytest
from sqlmodel import Session, select

from app.models import Invoice, PaymentLink
from tests.support import CUSTOMER, inbound, post_event, post_raw


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


def test_bad_signature_is_rejected_before_the_event_filter(client, kapso):
    # Even events the app ignores must be authenticated first.
    response = post_event(client, inbound("wamid.1"), secret="wrong", event="whatsapp.message.delivered")

    assert response.status_code == 401
    assert kapso.sent == []


def test_ignores_other_events(client, kapso):
    response = post_event(client, inbound("wamid.1"), event="whatsapp.message.delivered")

    assert response.status_code == 200
    assert kapso.sent == []


def test_unparseable_signed_payload_is_rejected(client, kapso):
    response = post_raw(client, b"not json")

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


def test_message_without_id_is_rejected_as_malformed(client, kapso, engine):
    payload = inbound("wamid.1", text="hola")
    del payload["message"]["id"]

    response = post_event(client, payload)

    assert response.status_code == 400
    assert kapso.sent == []
    with Session(engine) as session:
        assert session.exec(select(Invoice)).all() == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p["message"].update(id=123),
        lambda p: p["conversation"].update(phone_number=573001112233),
        lambda p: p["message"]["interactive"]["button_reply"].pop("id"),
        lambda p: p["message"]["interactive"]["button_reply"].update(id=1),
    ],
    ids=["numeric-id", "numeric-phone", "button-without-id", "numeric-button-id"],
)
def test_lenient_payload_shapes_are_still_processed(client, kapso, mutate):
    # Parsing must stay as permissive as the original dict-based handler: a 400 here
    # would make Kapso drop the message instead of retrying it.
    payload = inbound("wamid.1", button="other")
    mutate(payload)

    response = post_event(client, payload)

    assert response.status_code == 200
    assert response.json() == {"status": "processed"}
    assert len(kapso.sent) == 1


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-16"])
def test_bom_and_utf16_bodies_are_still_processed(client, kapso, encoding):
    raw = json.dumps(inbound("wamid.1", text="hola")).encode(encoding)

    response = post_raw(client, raw)

    assert response.status_code == 200
    assert len(kapso.sent) == 1


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p["message"].update(id=None),
        lambda p: p["conversation"].update(phone_number=None),
        lambda p: p.update(message="not-an-object"),
        lambda p: p["message"].update(interactive="not-an-object"),
    ],
    ids=["null-id", "null-phone", "message-string", "interactive-string"],
)
def test_unusable_payloads_are_rejected_without_side_effects(client, kapso, engine, mutate):
    # Accepted change from the refactor: these used to crash (500, retried in vain).
    payload = inbound("wamid.1", button="pay")
    mutate(payload)

    response = post_event(client, payload)

    assert response.status_code == 400
    assert kapso.sent == []
    with Session(engine) as session:
        assert session.exec(select(Invoice)).all() == []
