"""La allowlist de CORS acepta Vite local y rechaza orígenes no listados."""

ALLOWED_ORIGIN = "http://localhost:5173"


def test_allowed_origin_gets_cors_header(client):
    response = client.get("/api/health", headers={"Origin": ALLOWED_ORIGIN})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


def test_unlisted_origin_does_not_get_cors_header(client):
    response = client.get(
        "/api/health",
        headers={"Origin": "http://evil.example"},
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
