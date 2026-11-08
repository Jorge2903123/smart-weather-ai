"""
Endpoints REST de Smart Weather AI.

Prefijo global: /api
"""

from __future__ import annotations

import logging

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)

from app.config import settings
from app.db import log_weather
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
    # Las consultas pasivas (al montar la app) no se persisten en el historial.
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
    location: str | None = Form(
        default=None,
        description="Ubicación desde la que se tomó la foto (opcional).",
    ),
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

    # Solo se persisten análisis válidos; las imágenes descartadas no ensucian
    # el historial ni las métricas.
    if result.get("status") != "invalid_image":
        log_weather(
            location=location,
            temperature=None,
            rain_probability=result.get("rain_probability"),
            sky_condition=result.get("label"),
            query_type="vision",
        )

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
    destination = result.pop("destination", None)

    # Solo se persisten interacciones deliberadas del usuario.
    log_target = (
        (destination.get("current") or {})
        if destination and destination.get("resolved")
        else (context.get("current") or {})
    )
    log_forecast = (
        destination.get("forecast")
        if destination and destination.get("resolved")
        else context.get("forecast")
    )
    points = (log_forecast or {}).get("points") or []
    rain_values = [float(point.get("rain_probability") or 0.0) for point in points]
    rain_values.append(float(log_target.get("rain_probability") or 0.0))

    log_weather(
        location=log_target.get("location"),
        temperature=log_target.get("temperature"),
        rain_probability=max(rain_values, default=0.0),
        sky_condition=log_target.get("condition"),
        query_type="assistant_query",
    )

    return AssistantResponse(**result, destination=destination)
