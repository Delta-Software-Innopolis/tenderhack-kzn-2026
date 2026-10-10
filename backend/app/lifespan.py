"""Место для загрузки моделей и поисковых индексов при запуске."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # TODO: загрузить модели и индексы в app.state, освободить ресурсы после yield.
    yield
