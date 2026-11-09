"""Configuración común de pytest.

Las variables de entorno se definen ANTES de importar `app`, porque la
configuración y el engine de SQLAlchemy se crean al importar los módulos.
"""

from __future__ import annotations

import os
import secrets
import shutil
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

_TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="swa-pytest-"))
_TEST_DB_PATH = _TEST_DB_DIR / "smart_weather_test.db"
_TEST_ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN") or secrets.token_urlsafe(24)

os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.as_posix()}"
os.environ["ADMIN_TOKEN"] = _TEST_ADMIN_TOKEN
os.environ["CORS_ORIGINS"] = '["http://localhost:5173"]'
os.environ["GEMINI_API_KEY"] = ""
os.environ["VISION_MODEL_PATH"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal, WeatherLog, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def admin_token() -> str:
    return _TEST_ADMIN_TOKEN


@pytest.fixture(scope="session", autouse=True)
def _remove_test_database():
    yield
    engine.dispose()
    shutil.rmtree(_TEST_DB_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_database():
    init_db()
    with SessionLocal() as session:
        session.query(WeatherLog).delete()
        session.commit()
    yield
    with SessionLocal() as session:
        session.query(WeatherLog).delete()
        session.commit()


@pytest.fixture
def db_session():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def weather_log_count():
    def _count() -> int:
        with SessionLocal() as session:
            return session.query(WeatherLog).count()

    return _count


@pytest.fixture
def seed_weather_log(db_session):
    def _seed(**overrides):
        values = {
            "created_at": datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
            "date": date(2025, 1, 1),
            "location": "CDMX",
            "temperature": 22.0,
            "rain_probability": 10.0,
            "sky_condition": "Despejado",
            "query_type": "assistant_query",
        }
        values.update(overrides)
        entry = WeatherLog(**values)
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)
        return entry

    return _seed


@pytest.fixture
def location_payload() -> dict:
    return {
        "display_name": "Ciudad de México, CDMX",
        "city": "Ciudad de México",
        "state": "CDMX",
        "country": "México",
        "country_code": "mx",
        "latitude": 19.4326,
        "longitude": -99.1332,
        "source": "gps",
    }


@pytest.fixture
def current_weather_payload() -> dict:
    return {
        "location": "Ciudad de México, CDMX",
        "temperature": 22.5,
        "feels_like": 23.0,
        "humidity": 60,
        "wind_kph": 10.0,
        "uv_index": 4.0,
        "condition": "Cielo despejado",
        "sky_state": "Soleado",
        "emoji": "☀️",
        "rain_probability": 5,
        "latitude": 19.4326,
        "longitude": -99.1332,
        "country": "México",
        "country_code": "mx",
        "location_source": "gps",
        "data_source": "open-meteo",
        "updated_at": datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
    }
