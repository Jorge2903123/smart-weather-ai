"""Modelos ORM de Smart Weather AI."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import Column, Date, DateTime, Float, Integer, String

from app.db.database import Base

try:  # `zoneinfo` requiere el paquete tzdata en Windows.
    from zoneinfo import ZoneInfo

    MEXICO_CITY_TZ = ZoneInfo("America/Mexico_City")
except Exception:  # pragma: no cover - fallback si falta tzdata
    MEXICO_CITY_TZ = timezone(timedelta(hours=-6), "America/Mexico_City")


def mexico_city_now() -> datetime:
    """Hora actual con zona America/Mexico_City."""
    return datetime.now(MEXICO_CITY_TZ)


def mexico_city_today() -> date:
    return mexico_city_now().date()


class WeatherLog(Base):
    __tablename__ = "weather_logs"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(
        DateTime(timezone=True),
        default=mexico_city_now,
        nullable=False,
        index=True,
    )
    date = Column(Date, default=mexico_city_today, nullable=False, index=True)
    location = Column(String(255), nullable=False, default="No especificada")
    temperature = Column(Float, nullable=True)
    rain_probability = Column(Float, nullable=False, default=0.0)
    sky_condition = Column(String(255), nullable=False, default="No disponible")
    query_type = Column(String(32), nullable=False, index=True)
