import pytest

from tests.support import inbound, post_event

PASSWORD = "s3cret-admin"


@pytest.fixture
def admin_enabled(settings):
    settings.admin_password = PASSWORD


def test_admin_is_disabled_without_a_password(client):
    assert client.get("/admin", auth=("admin", PASSWORD)).status_code == 404


@pytest.mark.usefixtures("admin_enabled")
@pytest.mark.parametrize("auth", [None, ("admin", "wrong"), ("someone", PASSWORD), ("admin", "")])
def test_admin_requires_valid_credentials(client, auth):
    response = client.get("/admin", auth=auth)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Basic"


@pytest.mark.usefixtures("admin_enabled")
def test_admin_lists_invoices_and_webhook_events(client, seed):
    seed((8990000, "Internet - October"), (15430000, "Electricity - October"))
    post_event(client, inbound("wamid.1", text="hola"))
    post_event(client, inbound("wamid.1", text="hola"))

    page = client.get("/admin", auth=("admin", PASSWORD))

    assert page.status_code == 200
    assert "Internet - October" in page.text and "154,300.00 COP" in page.text
    assert "processed" in page.text and "duplicate" in page.text
    assert "wamid.1" in page.text


@pytest.mark.usefixtures("admin_enabled")
def test_admin_escapes_customer_content(client, seed):
    seed((100, "<b>bold</b>"))
    post_event(client, inbound("wamid.1", text="<script>alert(1)</script>"))

    page = client.get("/admin", auth=("admin", PASSWORD))

    assert "<script>" not in page.text and "<b>bold</b>" not in page.text
    assert "&lt;b&gt;bold&lt;/b&gt;" in page.text
