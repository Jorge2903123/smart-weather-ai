"""Contrato del pronóstico simulado."""

from datetime import datetime

from app.api import routes


def test_forecast_is_simulated_with_six_valid_points(
    client, monkeypatch, location_payload, current_weather_payload
):
    monkeypatch.setattr(
        routes,
        "_resolve_request_location",
        lambda lat, lon: location_payload,
    )
    monkeypatch.setattr(
        routes,
        "_weather_for_location",
        lambda location: current_weather_payload,
    )

    response = client.get(
        "/api/weather/forecast",
        params={"lat": 19.4326, "lon": -99.1332},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "simulated"
    assert len(payload["points"]) == 6

    for point in payload["points"]:
        datetime.strptime(point["time"], "%H:%M")
        assert isinstance(point["temperature"], (int, float))
        assert isinstance(point["rain_probability"], int)
        assert 0 <= point["rain_probability"] <= 100
