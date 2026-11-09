"""Autenticación y limpieza de las rutas de administración."""

from app.db import WeatherLog


def test_summary_requires_token(client):
    response = client.get("/api/admin/summary")

    assert response.status_code == 401


def test_summary_rejects_wrong_token(client):
    response = client.get(
        "/api/admin/summary",
        headers={"X-Admin-Token": "token-incorrecto"},
    )

    assert response.status_code == 403


def test_summary_accepts_valid_token(client, admin_token, seed_weather_log):
    seed_weather_log()

    response = client.get(
        "/api/admin/summary",
        headers={"X-Admin-Token": admin_token},
    )

    assert response.status_code == 200
    assert response.json()["total_logs"] == 1


def test_cleanup_without_token_does_not_delete(
    client, seed_weather_log, weather_log_count
):
    seed_weather_log(query_type="weather_check")
    seed_weather_log(query_type="assistant_query")
    before = weather_log_count()

    response = client.post("/api/admin/cleanup")

    assert response.status_code == 401
    assert weather_log_count() == before == 2


def test_cleanup_with_token_deletes_legacy_rows(
    client, admin_token, seed_weather_log, weather_log_count, db_session
):
    seed_weather_log(query_type="weather_check")
    seed_weather_log(query_type="assistant_query")

    response = client.post(
        "/api/admin/cleanup",
        params={"delete_legacy": "true", "dedupe": "false"},
        headers={"X-Admin-Token": admin_token},
    )

    assert response.status_code == 200
    assert response.json()["deleted_legacy"] == 1
    assert weather_log_count() == 1
    assert db_session.query(WeatherLog).one().query_type == "assistant_query"
