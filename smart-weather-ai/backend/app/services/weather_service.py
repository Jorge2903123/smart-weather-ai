"""
Proveedor de clima actual.

Prioridad:
1. Open-Meteo cuando hay coordenadas (GPS o destino geocodificado).
2. Clima simulado determinista si la API externa falla o no hay coordenadas.

El contrato de salida es el mismo en ambos casos para no romper el frontend.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from functools import lru_cache

import requests

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT = 6

_WMO_CONDITIONS = {
    0: ("Cielo despejado", "Soleado", "☀️"),
    1: ("Mayormente despejado", "Soleado", "🌤️"),
    2: ("Parcialmente nublado", "Nublado", "⛅"),
    3: ("Nublado", "Nublado", "☁️"),
    45: ("Niebla", "Nublado", "🌫️"),
    48: ("Niebla con escarcha", "Nublado", "🌫️"),
    51: ("Llovizna ligera", "Posible lluvia", "🌦️"),
    53: ("Llovizna", "Posible lluvia", "🌦️"),
    55: ("Llovizna intensa", "Posible lluvia", "🌦️"),
    56: ("Llovizna helada", "Posible lluvia", "🌧️"),
    57: ("Llovizna helada intensa", "Posible lluvia", "🌧️"),
    61: ("Lluvia ligera", "Lluvia", "🌧️"),
    63: ("Lluvia moderada", "Lluvia", "🌧️"),
    65: ("Lluvia intensa", "Lluvia", "🌧️"),
    66: ("Lluvia helada", "Lluvia", "🌧️"),
    67: ("Lluvia helada intensa", "Lluvia", "🌧️"),
    71: ("Nieve ligera", "Nieve", "🌨️"),
    73: ("Nieve moderada", "Nieve", "🌨️"),
    75: ("Nieve intensa", "Nieve", "🌨️"),
    77: ("Granos de nieve", "Nieve", "🌨️"),
    80: ("Chubascos ligeros", "Posible lluvia", "🌦️"),
    81: ("Chubascos moderados", "Lluvia", "🌧️"),
    82: ("Chubascos intensos", "Lluvia", "🌧️"),
    85: ("Chubascos de nieve", "Nieve", "🌨️"),
    86: ("Chubascos de nieve intensos", "Nieve", "🌨️"),
    95: ("Tormenta eléctrica", "Tormenta", "⛈️"),
    96: ("Tormenta con granizo", "Tormenta", "⛈️"),
    99: ("Tormenta fuerte con granizo", "Tormenta", "⛈️"),
}


def _seed_for(
    city: str,
    hour: int,
    latitude: float | None = None,
    longitude: float | None = None,
) -> int:
    """Semilla estable por ubicación + hora (incluye coordenadas si existen)."""
    key = f"{city.lower()}:{hour}"
    if latitude is not None and longitude is not None:
        key += f":{latitude:.3f}:{longitude:.3f}"
    digest = hashlib.sha256(key.encode()).hexdigest()
    return int(digest[:8], 16)


def _condition_for(humidity: int, temperature: float) -> tuple[str, str, str]:
    """Devuelve (condición, estado del cielo, emoji)."""
    if humidity >= 82:
        return "Lluvia ligera", "Posible lluvia", "🌧️"
    if humidity >= 70:
        return "Nublado", "Nublado", "☁️"
    if humidity >= 58:
        return "Parcialmente nublado", "Nublado", "🌤️"
    if temperature >= 30:
        return "Soleado y caluroso", "Soleado", "☀️"
    return "Cielo despejado", "Soleado", "☀️"


def _condition_for_code(code: int | str | None) -> tuple[str, str, str]:
    try:
        numeric = int(code)
    except (TypeError, ValueError):
        numeric = -1
    return _WMO_CONDITIONS.get(numeric, ("Condición variable", "Nublado", "🌤️"))


def _current_rain_probability(payload: dict) -> int:
    current = payload.get("current") or {}
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    probabilities = hourly.get("precipitation_probability") or []
    current_hour = str(current.get("time") or "")[:13]

    for time_value, probability in zip(times, probabilities):
        if str(time_value)[:13] == current_hour:
            return _clamp_probability(probability)

    if probabilities:
        return _clamp_probability(probabilities[0])
    return 0


def _clamp_probability(value: int | float | None) -> int:
    try:
        return int(max(0, min(100, round(float(value or 0)))))
    except (TypeError, ValueError):
        return 0


@lru_cache(maxsize=256)
def _open_meteo_cached(
    latitude: float,
    longitude: float,
    hour_key: str,
) -> dict:
    response = requests.get(
        OPEN_METEO_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,"
                "precipitation,rain,weather_code,wind_speed_10m"
            ),
            "hourly": "precipitation_probability",
            "forecast_days": 1,
            "timezone": "auto",
        },
        headers={"User-Agent": "smart-weather-ai/0.1 (proyecto-academico)"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    logger.info("Open-Meteo Weather URL consultada: %s", response.url)
    payload = response.json()
    current = payload.get("current") or {}

    temperature = round(float(current.get("temperature_2m") or 0), 1)
    humidity = int(max(0, min(100, round(float(current.get("relative_humidity_2m") or 0)))))
    wind = round(float(current.get("wind_speed_10m") or 0), 1)
    condition, sky_state, emoji = _condition_for_code(current.get("weather_code"))
    rain_probability = _current_rain_probability(payload)
    logger.info(
        "Open-Meteo Weather resultado (%.5f, %.5f): %.1f°C, lluvia %s%%, %s",
        latitude,
        longitude,
        temperature,
        rain_probability,
        condition,
    )

    return {
        "temperature": temperature,
        "feels_like": round(float(current.get("apparent_temperature") or temperature), 1),
        "humidity": humidity,
        "wind_kph": wind,
        "condition": condition,
        "sky_state": sky_state,
        "emoji": emoji,
        "rain_probability": rain_probability,
        "updated_at": datetime.now().astimezone(),
        "latitude": latitude,
        "longitude": longitude,
        "data_source": "open-meteo",
    }


def _simulated_weather(
    city: str,
    latitude: float | None,
    longitude: float | None,
    location_source: str,
) -> dict:
    now = datetime.now().astimezone()
    local_hour = now.hour
    seed = _seed_for(city, local_hour, latitude, longitude)

    base = 21.5 + 7.0 * ((seed % 100) / 100 - 0.5)
    daylight = 3.5 if 7 <= local_hour <= 18 else -2.5
    latitude_bias = 0.0
    if latitude is not None:
        latitude_bias = (abs(latitude) - 20) * -0.18
    temperature = round(base + daylight + latitude_bias, 1)

    humidity = 48 + (seed >> 8) % 42
    wind = round(4 + (seed >> 16) % 22 + ((seed >> 4) % 10) / 10, 1)
    condition, sky_state, emoji = _condition_for(humidity, temperature)

    rain_probability = int(max(0, min(100, (humidity - 55) * 1.6 + (seed >> 24) % 15)))
    if "lluvia" in condition.lower():
        rain_probability = max(rain_probability, 65)

    return {
        "location": city,
        "temperature": temperature,
        "feels_like": round(temperature + (humidity - 60) * 0.04 - wind * 0.06, 1),
        "humidity": humidity,
        "wind_kph": wind,
        "condition": condition,
        "sky_state": sky_state,
        "emoji": emoji,
        "rain_probability": rain_probability,
        "updated_at": now,
        "latitude": latitude,
        "longitude": longitude,
        "location_source": location_source,
        "data_source": "simulated",
    }


def get_current_weather(
    city: str = "Ubicación aproximada",
    latitude: float | None = None,
    longitude: float | None = None,
    *,
    location_source: str | None = None,
    use_live: bool = True,
) -> dict:
    now = datetime.now().astimezone()
    source = location_source or ("gps" if latitude is not None and longitude is not None else "default")

    if use_live and latitude is not None and longitude is not None:
        try:
            live = _open_meteo_cached(
                round(latitude, 4),
                round(longitude, 4),
                now.strftime("%Y%m%d%H"),
            )
            return {
                "location": city,
                **live,
                "location_source": source,
            }
        except Exception as exc:  # pragma: no cover - depende de la red externa
            logger.warning("Open-Meteo no disponible; usando clima simulado: %s", exc)

    return _simulated_weather(city, latitude, longitude, source)


def get_weather_for_location(location: dict) -> dict:
    """Obtiene el clima actual para una ubicación ya resuelta."""
    return get_current_weather(
        location.get("display_name") or "Ubicación aproximada",
        latitude=location.get("latitude"),
        longitude=location.get("longitude"),
        location_source=location.get("source"),
    )


def get_weather_for_destination(location: dict) -> dict:
    """Clima actual para un destino geocodificado (hotspot, Nominatim u Open-Meteo)."""
    return get_weather_for_location(location)
