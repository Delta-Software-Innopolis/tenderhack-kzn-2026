"""Роутер получения позиций и характеристик КТРУ; заготовка обработчиков."""

from fastapi import APIRouter

router = APIRouter(prefix="/catalog", tags=["catalog"])
