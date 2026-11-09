"""
Modelos Pydantic compartidos por la API.

Se usan tanto para validar las peticiones como para documentar las respuestas
en el Swagger autogenerado de FastAPI (/docs).
"""

import json
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Clima actual
# ---------------------------------------------------------------------------
class CurrentWeather(BaseModel):
    location: str = Field(..., examples=["Naucalpan de Juárez, Méx."])
    temperature: float = Field(..., description="Temperatura en °C", examples=[23.0])
    feels_like: float = Field(..., description="Sensación térmica en °C")
    humidity: int = Field(..., ge=0, le=100, description="Humedad relativa %")
    wind_kph: float = Field(..., ge=0, description="Viento en km/h")
    uv_index: float = Field(default=0.0, ge=0, le=20, description="Índice UV actual")
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
    status: Literal["ok", "invalid_image"] = "ok"
    description: str = Field(
        default="",
        examples=["Las nubes cubren la mayor parte del cielo."],
    )
    rain_probability: float = Field(
        default=0.0,
        ge=0,
        le=100,
        description="Probabilidad estimada de lluvia a partir de la imagen.",
    )
    has_image: bool = Field(
        default=True,
        description="Indica si se recibió y decodificó una imagen.",
    )
    is_valid: bool = Field(
        default=True,
        description="False si la imagen no corresponde a cielo abierto.",
    )
    sky_label: str = Field(
        default="",
        description="Etiqueta legible del cielo o del rechazo.",
    )
    message: str = Field(
        default="",
        description="Mensaje para el usuario cuando la imagen se rechaza.",
    )


# ---------------------------------------------------------------------------
# Asistente (Gemini)
# ---------------------------------------------------------------------------
class AssistantAskRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=1000)
    current_context: dict = Field(
        default_factory=dict,
        description="Métricas actuales, salida de visión y pronóstico.",
    )

    @field_validator("current_context")
    @classmethod
    def validate_current_context(cls, value: dict) -> dict:
        if len(value) > 32:
            raise ValueError("current_context no puede tener más de 32 claves.")

        try:
            serialized = json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("current_context debe ser serializable a JSON.") from exc

        if len(serialized) > 8 * 1024:
            raise ValueError("current_context supera el límite de 8 KB.")

        return value


class Recommendations(BaseModel):
    need_umbrella: bool = False
    need_jacket: bool = False
    need_sunscreen: bool = False
    summary: str = Field(default="", description="Recomendación corta y directa.")


class AssistantResponse(BaseModel):
    answer: str
    recommendations: Recommendations
    source: Literal["gemini", "fallback"]
    destination: dict | None = Field(
        default=None,
        description="Destino detectado y su clima comparativo, si aplica.",
    )


# ---------------------------------------------------------------------------
# Salud
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


# ---------------------------------------------------------------------------
# Admin / historial
# ---------------------------------------------------------------------------
QueryType = Literal[
    "assistant_query",
    "vision",
    # Valores legados que pueden existir en bases de datos antiguas.
    "weather_check",
    "destination_query",
]


class WeatherLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    date: date
    location: str
    temperature: float | None = None
    rain_probability: float = 0.0
    sky_condition: str
    query_type: QueryType


class AdminDaySummary(BaseModel):
    date: date
    queries: int
    avg_temperature: float | None = None
    max_rain_probability: float = 0.0
    by_type: dict[str, int] = Field(default_factory=dict)


class AdminSummaryResponse(BaseModel):
    total_logs: int
    days: list[AdminDaySummary]
    wettest_days: list[AdminDaySummary]


class AdminHistoryResponse(BaseModel):
    total: int
    items: list[WeatherLogOut]


class AdminCleanupResponse(BaseModel):
    deleted_legacy: int
    deleted_duplicates: int
    deleted_total: int
