from fastapi import APIRouter
from sqlmodel import text

from app.api.deps import SessionDep

router = APIRouter(tags=["health"])


@router.get("/health")
def health(session: SessionDep) -> dict[str, str]:
    """Liveness for the platform's healthcheck: the app is up and the database answers."""
    session.exec(text("SELECT 1"))
    return {"status": "ok"}
