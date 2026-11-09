"""Persistencia deliberada: clima pasivo no guarda; visión/asistente sí."""

from app.api import routes
from app.db import WeatherLog
from tests.image_helpers import sky_image


def test_passive_current_weather_does_not_insert_log(
    client, monkeypatch, current_weather_payload, weather_log_count
):
    monkeypatch.setattr(
        routes,
        "_resolve_request_location",
        lambda lat, lon: {
            "display_name": "Ciudad de México, CDMX",
            "latitude": lat,
            "longitude": lon,
            "source": "gps",
        },
    )
    monkeypatch.setattr(
        routes,
        "_weather_for_location",
        lambda location: current_weather_payload,
    )

    response = client.get(
        "/api/weather/current",
        params={"lat": 19.4326, "lon": -99.1332},
    )

    assert response.status_code == 200
    assert weather_log_count() == 0


def test_valid_vision_analysis_inserts_exactly_one_log(
    client, weather_log_count, db_session
):
    response = client.post(
        "/api/vision/analyze",
        files={"image": ("cielo.png", sky_image(), "image/png")},
        data={"location": "CDMX"},
    )

    assert response.status_code == 200
    assert response.json()["is_valid"] is True
    assert weather_log_count() == 1
    assert db_session.query(WeatherLog).one().query_type == "vision"


def test_assistant_request_inserts_exactly_one_log(
    client, monkeypatch, weather_log_count, db_session
):
    def fake_agent(prompt, context):
        return {
            "answer": "Lleva paraguas.",
            "recommendations": {
                "need_umbrella": True,
                "need_jacket": False,
                "need_sunscreen": False,
                "summary": "Lleva paraguas",
            },
            "source": "fallback",
            "destination": None,
        }

    monkeypatch.setattr(
        routes.gemini_agent,
        "generate_weather_response",
        fake_agent,
    )

    response = client.post(
        "/api/assistant/ask",
        json={
            "prompt": "¿Llevo paraguas?",
            "current_context": {
                "current": {
                    "location": "CDMX",
                    "temperature": 22.0,
                    "rain_probability": 45,
                    "condition": "Nublado",
                },
                "forecast": {"points": [{"rain_probability": 60}]},
            },
        },
    )

    assert response.status_code == 200
    assert weather_log_count() == 1
    assert db_session.query(WeatherLog).one().query_type == "assistant_query"
