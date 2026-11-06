"""
Modelos Pydantic compartidos por la API.

Se usan tanto para validar las peticiones como para documentar las respuestas
en el Swagger autogenerado de FastAPI (/docs).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Clima actual
# ---------------------------------------------------------------------------
class CurrentWeather(BaseModel):
    location: str = Field(..., examples=["Naucalpan de Juárez, Méx."])
    temperature: float = Field(..., description="Temperatura en °C", examples=[23.0])
    feels_like: float = Field(..., description="Sensación térmica en °C")
    humidity: int = Field(..., ge=0, le=100, description="Humedad relativa %")
    wind_kph: float = Field(..., ge=0, description="Viento en km/h")
    condition: str = Field(..., examples=["Parcialmente nublado"])
    sky_state: str = Field(..., examples=["Nublado"])
    emoji: str = Field(..., examples=["🌤️"])
    rain_probability: int | None = Field(default=None, ge=0, le=100)
    latitude: float | None = None
    longitude: float | None = None
    country: str | None = None
    country_code: str | None = None
    location_source: Literal["gps", "ip", "default", "geocoded"] = "default"
    data_source: Literal["open-meteo", "simulated"] = "simulated"
    updated_at: datetime


class ForecastPoint(BaseModel):
    time: str = Field(..., examples=["15:00"])
    temperature: float
    rain_probability: int = Field(..., ge=0, le=100)


class ForecastResponse(BaseModel):
    location: str
    source: Literal["lstm", "simulated"]
    points: list[ForecastPoint]


# ---------------------------------------------------------------------------
# Visión (CNN)
# ---------------------------------------------------------------------------
class SkyAnalysis(BaseModel):
    label: str = Field(..., examples=["Nubes densas"])
    confidence: float = Field(..., ge=0, le=1, examples=[0.87])
    state: str = Field(..., examples=["Posible lluvia"])
    source: Literal["cnn", "heuristic"] = "heuristic"


# ---------------------------------------------------------------------------
# Asistente (Gemini)
# ---------------------------------------------------------------------------
class AssistantAskRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=1000)
    current_context: dict = Field(
        default_factory=dict,
        description="Métricas actuales, salida de visión y pronóstico.",
    )


class Recommendations(BaseModel):
    need_umbrella: bool = False
    need_jacket: bool = False
    need_sunscreen: bool = False
    summary: str = Field(default="", description="Recomendación corta y directa.")


class AssistantResponse(BaseModel):
    answer: str
    recommendations: Recommendations
    source: Literal["gemini", "fallback"]


# ---------------------------------------------------------------------------
# Salud
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
