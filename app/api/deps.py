from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlmodel import Session

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.security import valid_admin_credentials
from app.services.messaging import KapsoClient, Messenger


def get_messenger(settings: Annotated[Settings, Depends(get_settings)]) -> Messenger:
    return KapsoClient(settings)


SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
MessengerDep = Annotated[Messenger, Depends(get_messenger)]


_basic_auth = HTTPBasic(auto_error=False)


def require_admin(
    settings: SettingsDep,
    credentials: Annotated[HTTPBasicCredentials | None, Depends(_basic_auth)],
) -> None:
    """Gate admin pages behind HTTP Basic; hide them entirely when no password is configured."""
    if not settings.admin_password:
        raise HTTPException(status_code=404)
    if credentials is None or not valid_admin_credentials(
        settings.admin_password, credentials.username, credentials.password
    ):
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})
