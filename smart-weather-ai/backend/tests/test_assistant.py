"""Validación del contexto y contrato del asistente (Gemini mockeado)."""

from app.api import routes


def _fake_agent(prompt, context):
    return {
        "answer": "Clima estable, disfruta el día.",
        "recommendations": {
            "need_umbrella": False,
            "need_jacket": False,
            "need_sunscreen": False,
            "summary": "Día agradable",
        },
        "source": "fallback",
        "destination": None,
    }


def test_context_with_more_than_32_keys_is_rejected(client, weather_log_count):
    context = {f"clave_{index}": index for index in range(33)}

    response = client.post(
        "/api/assistant/ask",
        json={"prompt": "¿Cómo está el clima?", "current_context": context},
    )

    assert response.status_code == 422
    assert weather_log_count() == 0


def test_context_larger_than_8kb_is_rejected(client, weather_log_count):
    context = {"current": {"note": "x" * 9000}}

    response = client.post(
        "/api/assistant/ask",
        json={"prompt": "¿Cómo está el clima?", "current_context": context},
    )

    assert response.status_code == 422
    assert weather_log_count() == 0


def test_normal_context_returns_200_with_mocked_gemini(client, monkeypatch):
    monkeypatch.setattr(
        routes.gemini_agent,
        "generate_weather_response",
        _fake_agent,
    )

    response = client.post(
        "/api/assistant/ask",
        json={
            "prompt": "¿Cómo está el clima?",
            "current_context": {
                "current": {"location": "CDMX", "temperature": 22.0},
                "forecast": {"points": [{"rain_probability": 10}]},
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Clima estable, disfruta el día."
