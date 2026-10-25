from fastapi import FastAPI

from app.api.main import api_router

app = FastAPI(title="Kapso payment collection")
app.include_router(api_router)
