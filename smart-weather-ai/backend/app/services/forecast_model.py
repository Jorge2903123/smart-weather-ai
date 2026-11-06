"""
Módulo de pronóstico a corto plazo (simulación de una LSTM).

En esta fase no se entrena una red recurrente: se modela su contrato de salida
(6 horas hacia adelante con temperatura y probabilidad de lluvia) usando una
curva determinista que respeta la humedad y la condición actual.

Cuando el equipo entrene la LSTM, solo debe reemplazar `_predict` por la
inferencia real manteniendo el mismo formato de respuesta.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import numpy as np


def _predict(current: dict, hours: int) -> list[dict]:
    """
    Genera la proyección horaria.

    - Temperatura: oscilación suave alrededor de la temperatura actual.
    - Lluvia: parte de la humedad y de la condición actual, con ruido acotado.
    """
    temperature = float(current.get("temperature", 23.0))
    humidity = float(current.get("humidity", 60))
    condition = str(current.get("condition", "")).lower()
    now = datetime.now()

    # Semilla estable por hora para que el resultado no cambie entre llamadas.
    rng = np.random.default_rng(seed=now.hour * 31 + now.day)

    current_rain = float(current.get("rain_probability", 0) or 0)
    base_rain = max(0.0, current_rain * 0.85)
    if "lluvia" in condition or "tormenta" in condition:
        base_rain = max(base_rain, 55.0)
    elif "nublado" in condition:
        base_rain = max(base_rain, 25.0)
    base_rain += max(0.0, humidity - 60) * 0.8

    points: list[dict] = []
    for offset in range(1, hours + 1):
        target = now + timedelta(hours=offset)

        # Curva diurna: mínimo ~6h, máximo ~15h.
        daily = math.sin((target.hour - 6) / 24 * 2 * math.pi)
        temp = temperature + daily * 2.4 + float(rng.normal(0, 0.4))

        rain = base_rain + daily * 8 + float(rng.normal(0, 6))
        rain = int(max(0, min(100, round(rain))))

        points.append(
            {
                "time": target.strftime("%H:00"),
                "temperature": round(temp, 1),
                "rain_probability": rain,
            }
        )

    return points


def generate_forecast(current: dict, hours: int = 6) -> dict:
    """Devuelve el pronóstico listo para serializar en la API."""
    return {
        "location": current.get("location", "Mi ubicación"),
        "source": "simulated",
        "points": _predict(current, hours),
    }
