"""
Configuración central del backend.

Todas las variables se leen desde el archivo `.env` (o variables de entorno
del sistema). Pydantic Settings valida los tipos y entrega valores por defecto
seguros para el entorno de desarrollo local.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Gemini -------------------------------------------------------------
    # Se deja opcional para que la API arranque incluso sin clave; el agente
    # usará un razonador local de respaldo cuando falte la credencial.
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"

    # --- Servidor -----------------------------------------------------------
    # 0.0.0.0 permite que un iPhone en la misma red local alcance la API.
    host: str = "0.0.0.0"
    port: int = 8000
    app_name: str = "Smart Weather AI"
    app_version: str = "0.1.0"

    # --- CORS ---------------------------------------------------------------
    # En desarrollo se permite cualquier origen para evitar bloqueos desde
    # Safari iOS / Expo / túneles (Cloudflare, Ngrok).
    cors_origins: list[str] = ["*"]

    # --- Modelos ------------------------------------------------------------
    # Ruta opcional a los pesos de la CNN (por ejemplo un .pt de PyTorch).
    # Si no existe, vision_model.py usa el clasificador heurístico de respaldo.
    vision_model_path: str | None = None

    # --- Base de datos ------------------------------------------------------
    # Por defecto SQLite en backend/smart_weather.db. Se puede sobrescribir.
    database_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Devuelve una instancia cacheada de la configuración."""
    return Settings()


settings = get_settings()
