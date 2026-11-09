"""
Endpoints de administración y métricas acumuladas.

Prefijo: /api/admin
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import APIKeyHeader
from sqlalchemy import func, select

from app.config import settings
from app.db import SessionLocal, WeatherLog, cleanup_logs
from app.schemas import (
    AdminCleanupResponse,
    AdminDaySummary,
    AdminHistoryResponse,
    AdminSummaryResponse,
    WeatherLogOut,
)

_admin_token_header = APIKeyHeader(name="X-Admin-Token", auto_error=False)


def require_admin_token(
    token: str | None = Depends(_admin_token_header),
) -> None:
    """Valida el token de administrador en todas las rutas /api/admin/*."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de administrador requerido.",
            headers={"WWW-Authenticate": "X-Admin-Token"},
        )

    expected = (settings.admin_token or "").strip()
    valid = bool(expected) and secrets.compare_digest(
        token.strip().encode("utf-8"),
        expected.encode("utf-8"),
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token de administrador inválido.",
        )


router = APIRouter(
    prefix="/api/admin",
    tags=["Admin"],
    dependencies=[Depends(require_admin_token)],
)


@router.get("/summary", response_model=AdminSummaryResponse)
def admin_summary() -> AdminSummaryResponse:
    """Métricas acumuladas agrupadas por día."""
    with SessionLocal() as session:
        total_logs = session.scalar(select(func.count(WeatherLog.id))) or 0

        rows = session.execute(
            select(
                WeatherLog.date,
                func.count(WeatherLog.id),
                func.avg(WeatherLog.temperature),
                func.max(WeatherLog.rain_probability),
            )
            .group_by(WeatherLog.date)
            .order_by(WeatherLog.date.desc())
        ).all()

        type_rows = session.execute(
            select(
                WeatherLog.date,
                WeatherLog.query_type,
                func.count(WeatherLog.id),
            ).group_by(WeatherLog.date, WeatherLog.query_type)
        ).all()

    by_type: dict[object, dict[str, int]] = {}
    for day, query_type, count in type_rows:
        by_type.setdefault(day, {})[query_type] = int(count)

    days: list[AdminDaySummary] = []
    for day, count, avg_temp, max_rain in rows:
        days.append(
            AdminDaySummary(
                date=day,
                queries=int(count),
                avg_temperature=round(float(avg_temp), 1) if avg_temp is not None else None,
                max_rain_probability=round(float(max_rain or 0.0), 1),
                by_type=by_type.get(day, {}),
            )
        )

    wettest_days = sorted(
        days, key=lambda item: item.max_rain_probability, reverse=True
    )[:5]

    return AdminSummaryResponse(
        total_logs=int(total_logs),
        days=days,
        wettest_days=wettest_days,
    )


@router.get("/history", response_model=AdminHistoryResponse)
def admin_history(
    limit: int = Query(default=50, ge=1, le=500),
) -> AdminHistoryResponse:
    """Historial reciente de consultas (más nuevas primero)."""
    with SessionLocal() as session:
        total = session.scalar(select(func.count(WeatherLog.id))) or 0
        entries = session.scalars(
            select(WeatherLog)
            .order_by(WeatherLog.created_at.desc(), WeatherLog.id.desc())
            .limit(limit)
        ).all()

    items = [WeatherLogOut.model_validate(entry) for entry in entries]
    return AdminHistoryResponse(total=int(total), items=items)


@router.post("/cleanup", response_model=AdminCleanupResponse)
def admin_cleanup(
    delete_legacy: bool = Query(
        default=True,
        description="Elimina registros pasivos antiguos (weather_check, destination_query).",
    ),
    dedupe: bool = Query(
        default=True,
        description="Elimina duplicados exactos conservando el más antiguo.",
    ),
) -> AdminCleanupResponse:
    """Depura registros huérfanos, pasivos o duplicados del historial."""
    result = cleanup_logs(delete_legacy=delete_legacy, dedupe=dedupe)
    return AdminCleanupResponse(**result)
