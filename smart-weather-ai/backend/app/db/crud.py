"""Operaciones de escritura/lectura sobre el historial de consultas."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, func, select

from app.db.database import SessionLocal
from app.db.models import WeatherLog, mexico_city_now

logger = logging.getLogger(__name__)

LEGACY_QUERY_TYPES = ("weather_check", "destination_query")


def log_weather(
    *,
    location: str | None,
    temperature: float | None,
    rain_probability: float | None,
    sky_condition: str | None,
    query_type: str,
) -> WeatherLog | None:
    """
    Guarda una consulta en `weather_logs`.

    Nunca lanza: si la base de datos falla, la API principal sigue respondiendo.
    """
    now = mexico_city_now()
    entry = WeatherLog(
        created_at=now,
        date=now.date(),
        location=(location or "No especificada")[:255],
        temperature=temperature,
        rain_probability=float(rain_probability or 0.0),
        sky_condition=(sky_condition or "No disponible")[:255],
        query_type=query_type,
    )

    try:
        with SessionLocal() as session:
            session.add(entry)
            session.commit()
            session.refresh(entry)
            session.expunge(entry)
        return entry
    except Exception:  # pragma: no cover - depende del entorno
        logger.exception("No se pudo guardar el registro de clima")
        return None


def serialize_log(entry: WeatherLog) -> dict[str, Any]:
    """Convierte un registro en un dict apto para Pydantic."""
    return {
        "id": entry.id,
        "created_at": entry.created_at,
        "date": entry.date,
        "location": entry.location,
        "temperature": entry.temperature,
        "rain_probability": entry.rain_probability,
        "sky_condition": entry.sky_condition,
        "query_type": entry.query_type,
    }


def cleanup_logs(
    *,
    delete_legacy: bool = True,
    dedupe: bool = True,
) -> dict[str, int]:
    """
    Depura el historial:

    - Elimina registros legados generados por consultas pasivas
      (`weather_check`, `destination_query`).
    - Elimina duplicados exactos conservando el registro más antiguo.

    Devuelve el conteo de registros eliminados por categoría.
    """
    deleted_legacy = 0
    deleted_duplicates = 0

    try:
        with SessionLocal() as session:
            if delete_legacy:
                result = session.execute(
                    delete(WeatherLog).where(
                        WeatherLog.query_type.in_(LEGACY_QUERY_TYPES)
                    )
                )
                deleted_legacy = int(result.rowcount or 0)

            if dedupe:
                keep_ids = select(func.min(WeatherLog.id)).group_by(
                    WeatherLog.created_at,
                    WeatherLog.date,
                    WeatherLog.location,
                    WeatherLog.temperature,
                    WeatherLog.rain_probability,
                    WeatherLog.sky_condition,
                    WeatherLog.query_type,
                )
                result = session.execute(
                    delete(WeatherLog).where(WeatherLog.id.notin_(keep_ids))
                )
                deleted_duplicates = int(result.rowcount or 0)

            session.commit()
    except Exception:  # pragma: no cover - depende del entorno
        logger.exception("No se pudo depurar el historial de clima")
        raise

    total = deleted_legacy + deleted_duplicates
    logger.info(
        "Depuración de historial: %s legados, %s duplicados (%s total)",
        deleted_legacy,
        deleted_duplicates,
        total,
    )
    return {
        "deleted_legacy": deleted_legacy,
        "deleted_duplicates": deleted_duplicates,
        "deleted_total": total,
    }
