"""Роутер анализа описания товара; обработчики будут добавлены с pipeline."""

from fastapi import APIRouter

router = APIRouter(prefix="/analysis", tags=["analysis"])
