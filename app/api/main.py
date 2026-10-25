from fastapi import APIRouter

from app.api.routers import admin, checkout, health
from app.api.routers.webhooks import kapso

api_router = APIRouter()
api_router.include_router(kapso.router)
api_router.include_router(checkout.router)
api_router.include_router(admin.router)
api_router.include_router(health.router)
