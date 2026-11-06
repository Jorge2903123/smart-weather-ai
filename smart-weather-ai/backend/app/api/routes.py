"""
Endpoints REST de Smart Weather AI.

Prefijo global: /api
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from app.config import settings
from app.schemas import (
    AssistantAskRequest,
    AssistantResponse,
    CurrentWeather,
    ForecastResponse,
    HealthResponse,
    SkyAnalysis,
)
from app.services import (
    forecast_model,
    gemini_agent,
    location_service,
    vision_model,
    weather_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Smart Weather AI"])

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB


# ---------------------------------------------------------------------------
# Salud
# ---------------------------------------------------------------------------
@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
    )


# ---------------------------------------------------------------------------
# Clima
# ---------------------------------------------------------------------------
def _resolve_request_location(
    lat: float | None, lon: float | None
) -> dict:
    """Valida coordenadas y resuelve la ubicación (GPS o fallback por IP)."""
    if (lat is None) != (lon is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debes enviar 'lat' y 'lon' juntos.",
        )
    return location_service.resolve_location(lat, lon)


def _weather_for_location(location: dict) -> dict:
    data = weather_service.get_weather_for_location(location)
    data["country"] = location.get("country")
    data["country_code"] = location.get("country_code")
    return data


@router.get("/weather/current", response_model=CurrentWeather)
def weather_current(
    lat: float | None = Query(default=None, ge=-90, le=90),
    lon: float | None = Query(default=None, ge=-180, le=180),
) -> CurrentWeather:
    location = _resolve_request_location(lat, lon)
    return CurrentWeather(**_weather_for_location(location))


@router.get("/weather/forecast", response_model=ForecastResponse)
def weather_forecast(
    lat: float | None = Query(default=None, ge=-90, le=90),
    lon: float | None = Query(default=None, ge=-180, le=180),
    hours: int = Query(default=6, ge=1, le=24),
) -> ForecastResponse:
    location = _resolve_request_location(lat, lon)
    current = _weather_for_location(location)
    data = forecast_model.generate_forecast(current, hours=hours)
    return ForecastResponse(**data)


# ---------------------------------------------------------------------------
# Visión
# ---------------------------------------------------------------------------
@router.post("/vision/analyze", response_model=SkyAnalysis)
async def analyze_sky(
    image: UploadFile = File(..., description="Foto del cielo (JPEG/PNG/WebP)"),
) -> SkyAnalysis:
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="El archivo debe ser una imagen.",
        )

    content = await image.read()
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="La imagen supera el límite de 10 MB.",
        )

    try:
        result = vision_model.analyze_sky_image(content)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    return SkyAnalysis(**result)


# ---------------------------------------------------------------------------
# Asistente
# ---------------------------------------------------------------------------
@router.post("/assistant/ask", response_model=AssistantResponse)
def assistant_ask(payload: AssistantAskRequest) -> AssistantResponse:
    context = payload.current_context or {}

    # Si el cliente no envía contexto, se construye uno mínimo con datos actuales.
    if not context:
        location = location_service.resolve_location(None, None)
        current = _weather_for_location(location)
        context = {
            "current": current,
            "forecast": forecast_model.generate_forecast(current),
        }

    result = gemini_agent.generate_weather_response(payload.prompt, context)
    return AssistantResponse(**result)
