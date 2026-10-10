"""Создание FastAPI и подключение роутеров."""

from fastapi import FastAPI

from app.api import analysis, catalog, health
from app.config import get_settings
from app.lifespan import lifespan

app = FastAPI(title=get_settings().app_name, lifespan=lifespan)
app.include_router(health.router)
app.include_router(analysis.router)
app.include_router(catalog.router)
