"""
Configuración de la base de datos SQLite.

El archivo `smart_weather.db` se ubica en la raíz de `backend/`, sin importar
desde qué directorio se ejecute uvicorn. La ruta se puede sobrescribir con la
variable de entorno `DATABASE_URL`.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = BACKEND_DIR / "smart_weather.db"

DATABASE_URL = settings.database_url or f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def init_db() -> None:
    """Crea las tablas si aún no existen."""
    from app.db import models  # noqa: F401  (registra los modelos en Base)

    Base.metadata.create_all(bind=engine)
