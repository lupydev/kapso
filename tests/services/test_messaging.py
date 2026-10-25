import pytest

from app.services.messaging import KapsoError


@pytest.mark.parametrize(
    ("status_code", "retryable"), [(400, False), (403, False), (422, False), (429, True), (500, True), (503, True)]
)
def test_kapso_errors_are_classified_by_status(status_code, retryable):
    assert KapsoError.from_status(status_code, "body").retryable is retryable
