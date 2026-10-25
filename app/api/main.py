from fastapi import APIRouter

from app.api.routers import checkout
from app.api.routers.webhooks import kapso

api_router = APIRouter()
api_router.include_router(kapso.router)
api_router.include_router(checkout.router)
