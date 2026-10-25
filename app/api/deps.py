from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.services.messaging import KapsoClient, Messenger


def get_messenger(settings: Annotated[Settings, Depends(get_settings)]) -> Messenger:
    return KapsoClient(settings)


SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
MessengerDep = Annotated[Messenger, Depends(get_messenger)]
