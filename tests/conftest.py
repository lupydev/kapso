import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

import app.models  # noqa: F401  (register tables for create_all)
from app.api.deps import get_messenger
from app.main import app
from app.core.config import Settings, get_settings
from app.core.db import get_session
from tests.support import SECRET, FakeKapso


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def kapso():
    return FakeKapso()


@pytest.fixture
def client(engine, kapso):
    def session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_messenger] = lambda: kapso
    app.dependency_overrides[get_settings] = lambda: Settings(
        kapso_api_key="k",
        kapso_phone_number_id="123",
        kapso_webhook_secret=SECRET,
        public_base_url="https://example.test",
        invoice_amount_cents=5000000,
        invoice_currency="COP",
    )
    yield TestClient(app)
    app.dependency_overrides.clear()
