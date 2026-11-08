"""
Resolución de ubicación para Smart Weather AI.

Prioridad:
1. Coordenadas GPS enviadas por el cliente -> geocodificación inversa (Nominatim).
2. Sin coordenadas -> ubicación aproximada por IP pública (ipapi.co).
3. Si ambos fallan -> etiqueta neutra para no romper la app.

Geocodificación de destinos (100% dinámica, sin listas fijas):
1. Nominatim con sesgo espacial alrededor de la ubicación del usuario.
2. Photon con el mismo sesgo (segundo proveedor).
3. Fallback sin sesgo restringido a México.
4. Open-Meteo Geocoding como último recurso.

Los resultados se cachean para respetar las políticas de uso de los servicios
gratuitos y para que las llamadas simultáneas de clima + pronóstico no dupliquen
peticiones externas.
"""

from __future__ import annotations

import logging
import threading
import time
import unicodedata
from functools import lru_cache
from typing import Any

import requests

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
PHOTON_URL = "https://photon.komoot.io/api"
OPEN_METEO_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
IPAPI_URL = "https://ipapi.co/json/"
USER_AGENT = "SmartWeatherAI-App/1.0"
REQUEST_TIMEOUT = 4
IP_CACHE_TTL = 600  # 10 minutos
SEARCH_VIEWBOX_SPAN = 1.2  # ~120 km de radio para el sesgo de proximidad

_STATE_ABBREVIATIONS = {
    "aguascalientes": "Ags.",
    "baja california": "B.C.",
    "baja california sur": "B.C.S.",
    "campeche": "Camp.",
    "chiapas": "Chis.",
    "chihuahua": "Chih.",
    "ciudad de méxico": "CDMX",
    "distrito federal": "CDMX",
    "mexico city": "CDMX",
    "coahuila": "Coah.",
    "colima": "Col.",
    "durango": "Dgo.",
    "estado de méxico": "Méx.",
    "guanajuato": "Gto.",
    "guerrero": "Gro.",
    "hidalgo": "Hgo.",
    "jalisco": "Jal.",
    "michoacán": "Mich.",
    "morelos": "Mor.",
    "méxico": "Méx.",
    "mexico": "Méx.",
    "nayarit": "Nay.",
    "nuevo león": "N.L.",
    "oaxaca": "Oax.",
    "puebla": "Pue.",
    "querétaro": "Qro.",
    "quintana roo": "Q. Roo",
    "san luis potosí": "S.L.P.",
    "sinaloa": "Sin.",
    "sonora": "Son.",
    "tabasco": "Tab.",
    "tamaulipas": "Tamps.",
    "tlaxcala": "Tlax.",
    "veracruz": "Ver.",
    "yucatán": "Yuc.",
    "zacatecas": "Zac.",
}

_ip_cache: dict[str, Any] = {"data": None, "timestamp": 0.0}
_ip_lock = threading.Lock()
_reverse_lock = threading.Lock()
_search_lock = threading.Lock()


def _short_state(state: str | None) -> str | None:
    if not state:
        return None
    return _STATE_ABBREVIATIONS.get(state.strip().lower(), state)


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.strip().lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _nominatim_destination_queries(query: str) -> list[str]:
    normalized = _normalize_text(query)
    candidates: list[str] = []
    if "mexico" not in normalized and "cdmx" not in normalized:
        candidates.append(f"{query}, México")
    candidates.append(query)
    return list(dict.fromkeys(candidates))


def _open_meteo_destination_queries(query: str) -> list[str]:
    normalized = _normalize_text(query)
    candidates = [query]
    if "mexico" not in normalized and "cdmx" not in normalized:
        candidates.append(f"{query}, México")
    return list(dict.fromkeys(candidates))


def _build_location(
    *,
    city: str | None,
    state: str | None,
    country: str | None,
    latitude: float | None,
    longitude: float | None,
    source: str,
    country_code: str | None = None,
) -> dict:
    state = _short_state(state)
    parts = [part for part in (city, state) if part]
    display_name = ", ".join(parts) or country or "Ubicación aproximada"

    return {
        "display_name": display_name,
        "city": city,
        "state": state,
        "country": country,
        "country_code": (country_code or "").lower() or None,
        "latitude": latitude,
        "longitude": longitude,
        "source": source,
    }


@lru_cache(maxsize=256)
def _reverse_geocode_cached(latitude: float, longitude: float) -> dict:
    """Geocodificación inversa cacheada. La clave se redondea a ~11 m."""
    response = requests.get(
        NOMINATIM_URL,
        params={
            "lat": latitude,
            "lon": longitude,
            "format": "jsonv2",
            "addressdetails": 1,
            "accept-language": "es",
        },
        headers={"User-Agent": USER_AGENT, "Accept-Language": "es"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    address = payload.get("address") or {}

    city = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("municipality")
        or address.get("county")
        or address.get("state_district")
    )
    state = address.get("state") or address.get("region")
    country = address.get("country")

    return _build_location(
        city=city,
        state=state,
        country=country,
        country_code=address.get("country_code"),
        latitude=latitude,
        longitude=longitude,
        source="gps",
    )


@lru_cache(maxsize=256)
def _geocode_place_cached(
    query: str,
    near_latitude: float | None,
    near_longitude: float | None,
    country_code: str | None,
) -> dict | None:
    """Busca un lugar por nombre y devuelve su ubicación normalizada."""
    params: dict[str, Any] = {
        "q": query,
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": 5,
        "accept-language": "es",
    }
    if country_code:
        params["countrycodes"] = country_code.lower()
    if near_latitude is not None and near_longitude is not None:
        params["viewbox"] = ",".join(
            f"{value:.4f}"
            for value in (
                near_longitude - SEARCH_VIEWBOX_SPAN,
                near_latitude + SEARCH_VIEWBOX_SPAN,
                near_longitude + SEARCH_VIEWBOX_SPAN,
                near_latitude - SEARCH_VIEWBOX_SPAN,
            )
        )
        params["bounded"] = 0

    response = requests.get(
        NOMINATIM_SEARCH_URL,
        params=params,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "es"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    logger.info("Nominatim URL consultada: %s", response.url)
    results = response.json()
    if not results:
        logger.info("Nominatim sin resultados para '%s'", query)
        return None

    result = results[0]
    logger.info(
        "Nominatim resultado para '%s': %s",
        query,
        result.get("display_name") or result.get("name"),
    )
    address = result.get("address") or {}
    city = (
        address.get("suburb")
        or address.get("neighbourhood")
        or address.get("village")
        or address.get("town")
        or address.get("city")
        or address.get("municipality")
        or address.get("county")
        or result.get("name")
        or query
    )
    state = address.get("state") or address.get("region")
    country = address.get("country")
    latitude = result.get("lat")
    longitude = result.get("lon")

    try:
        latitude = float(latitude) if latitude is not None else None
        longitude = float(longitude) if longitude is not None else None
    except (TypeError, ValueError):
        latitude = None
        longitude = None

    return _build_location(
        city=city,
        state=state,
        country=country,
        country_code=address.get("country_code"),
        latitude=latitude,
        longitude=longitude,
        source="geocoded",
    )


@lru_cache(maxsize=256)
def _photon_geocode_cached(
    query: str,
    near_latitude: float | None,
    near_longitude: float | None,
) -> dict | None:
    """Búsqueda en Photon (Komoot) con sesgo opcional por proximidad."""
    params: dict[str, Any] = {
        "q": query,
        "limit": 5,
        "lang": "es",
    }
    if near_latitude is not None and near_longitude is not None:
        params["lat"] = near_latitude
        params["lon"] = near_longitude

    response = requests.get(
        PHOTON_URL,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    logger.info("Photon URL consultada: %s", response.url)

    features = (response.json() or {}).get("features") or []
    if not features:
        logger.info("Photon sin resultados para '%s'", query)
        return None

    # Prioriza resultados mexicanos cuando el proveedor devuelve varios países.
    feature = next(
        (
            item
            for item in features
            if str((item.get("properties") or {}).get("countrycode", "")).lower()
            == "mx"
        ),
        features[0],
    )
    properties = feature.get("properties") or {}
    coordinates = (feature.get("geometry") or {}).get("coordinates") or []
    if len(coordinates) < 2:
        return None

    city = (
        properties.get("city")
        or properties.get("district")
        or properties.get("locality")
        or properties.get("name")
        or query
    )
    logger.info(
        "Photon resultado para '%s': %s",
        query,
        properties.get("name") or city,
    )
    return _build_location(
        city=city,
        state=properties.get("state"),
        country=properties.get("country"),
        country_code=properties.get("countrycode"),
        latitude=coordinates[1],
        longitude=coordinates[0],
        source="geocoded",
    )


@lru_cache(maxsize=256)
def _open_meteo_geocode_cached(query: str) -> dict | None:
    response = requests.get(
        OPEN_METEO_GEOCODE_URL,
        params={
            "name": query,
            "count": 1,
            "language": "es",
            "format": "json",
        },
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    logger.info("Open-Meteo Geocoding URL consultada: %s", response.url)
    results = response.json().get("results") or []
    if not results:
        logger.info("Open-Meteo Geocoding sin resultados para '%s'", query)
        return None

    result = results[0]
    location = _build_location(
        city=result.get("name"),
        state=result.get("admin1") or result.get("admin2"),
        country=result.get("country"),
        country_code=result.get("country_code"),
        latitude=result.get("latitude"),
        longitude=result.get("longitude"),
        source="geocoded",
    )
    logger.info("Open-Meteo Geocoding resultado para '%s': %s", query, location)
    return location


def _has_coordinates(location: dict | None) -> bool:
    return bool(
        location
        and location.get("latitude") is not None
        and location.get("longitude") is not None
    )


def dynamic_geocode(
    normalized_name: str,
    user_lat: float | None = None,
    user_lon: float | None = None,
) -> dict | None:
    """
    Geocodifica un topónimo con sesgo espacial hacia la ubicación del usuario.

    Fases:
    1. Nominatim con `viewbox` de ±1.2° (~120 km) alrededor del usuario.
    2. Photon con el mismo sesgo (proveedor alterno).
    3. Fallback sin sesgo restringido a México.
    4. Open-Meteo Geocoding como último recurso.
    """
    query = (normalized_name or "").strip()
    if not query:
        return None

    has_bias = user_lat is not None and user_lon is not None
    logger.info(
        "Resolviendo destino '%s' (sesgo=%s)",
        query,
        f"{user_lat:.4f},{user_lon:.4f}" if has_bias else "sin GPS",
    )

    nominatim_queries = _nominatim_destination_queries(query)
    open_meteo_queries = _open_meteo_destination_queries(query)

    if has_bias:
        for candidate in nominatim_queries:
            try:
                with _search_lock:
                    location = _geocode_place_cached(
                        candidate, user_lat, user_lon, "mx"
                    )
            except requests.Timeout as exc:
                logger.warning("Nominatim timeout para '%s': %s", candidate, exc)
                location = None
            except Exception as exc:  # pragma: no cover - depende de la red externa
                logger.warning("Nominatim falló para '%s': %s", candidate, exc)
                location = None
            if _has_coordinates(location):
                logger.info(
                    "Nominatim con sesgo: '%s' -> %s",
                    query,
                    location.get("display_name"),
                )
                return location

        for candidate in nominatim_queries:
            try:
                with _search_lock:
                    location = _photon_geocode_cached(candidate, user_lat, user_lon)
            except requests.Timeout as exc:
                logger.warning("Photon timeout para '%s': %s", candidate, exc)
                location = None
            except Exception as exc:  # pragma: no cover - depende de la red externa
                logger.warning("Photon falló para '%s': %s", candidate, exc)
                location = None
            if _has_coordinates(location):
                logger.info(
                    "Photon con sesgo: '%s' -> %s",
                    query,
                    location.get("display_name"),
                )
                return location

    for candidate in nominatim_queries:
        try:
            with _search_lock:
                location = _geocode_place_cached(candidate, None, None, "mx")
        except requests.Timeout as exc:
            logger.warning("Nominatim timeout para '%s': %s", candidate, exc)
            location = None
        except Exception as exc:  # pragma: no cover - depende de la red externa
            logger.warning("Nominatim falló para '%s': %s", candidate, exc)
            location = None
        if _has_coordinates(location):
            logger.info(
                "Nominatim sin sesgo: '%s' -> %s",
                query,
                location.get("display_name"),
            )
            return location

    for candidate in nominatim_queries:
        try:
            with _search_lock:
                location = _photon_geocode_cached(candidate, None, None)
        except Exception as exc:  # pragma: no cover - depende de la red externa
            logger.warning("Photon falló para '%s': %s", candidate, exc)
            location = None
        if _has_coordinates(location):
            logger.info(
                "Photon sin sesgo: '%s' -> %s",
                query,
                location.get("display_name"),
            )
            return location

    for candidate in open_meteo_queries:
        try:
            location = _open_meteo_geocode_cached(candidate)
        except requests.Timeout as exc:
            logger.warning("Open-Meteo timeout para '%s': %s", candidate, exc)
            break
        except Exception as exc:  # pragma: no cover - depende de la red externa
            logger.warning("Open-Meteo Geocoding falló para '%s': %s", candidate, exc)
            continue
        if _has_coordinates(location):
            logger.info(
                "Open-Meteo Geocoding: '%s' -> %s",
                query,
                location.get("display_name"),
            )
            return location

    logger.info("No se pudo geocodificar el destino '%s'", query)
    return None


def geocode_destination(
    destination_name: str,
    user_lat: float | None = None,
    user_lon: float | None = None,
) -> dict | None:
    """Compatibilidad: geocodificación dinámica con sesgo por proximidad."""
    return dynamic_geocode(destination_name, user_lat, user_lon)


def resolve_coordinates(latitude: float, longitude: float) -> dict:
    """Obtiene una etiqueta legible a partir de coordenadas GPS."""
    # Redondeo para cachear y evitar golpear Nominatim con variaciones mínimas.
    lat_key = round(latitude, 4)
    lon_key = round(longitude, 4)

    try:
        # Serializa la primera consulta; las siguientes ya vienen de la caché.
        with _reverse_lock:
            return _reverse_geocode_cached(lat_key, lon_key)
    except Exception as exc:  # pragma: no cover - depende de la red externa
        logger.warning("Geocodificación inversa falló: %s", exc)
        return _build_location(
            city=None,
            state=None,
            country=None,
            latitude=latitude,
            longitude=longitude,
            source="gps",
        )


def resolve_ip_location() -> dict:
    """Fallback: estima la ubicación con la IP pública del servidor/cliente."""
    now = time.time()
    cached = _ip_cache.get("data")
    if cached and now - float(_ip_cache.get("timestamp", 0)) < IP_CACHE_TTL:
        return cached

    # Evita que clima + pronóstico consulten ipapi.co al mismo tiempo.
    with _ip_lock:
        now = time.time()
        cached = _ip_cache.get("data")
        if cached and now - float(_ip_cache.get("timestamp", 0)) < IP_CACHE_TTL:
            return cached

        try:
            response = requests.get(
                IPAPI_URL,
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()

            if payload.get("error"):
                raise ValueError(payload.get("reason", "ipapi.co devolvió un error"))

            city = payload.get("city")
            region = payload.get("region")
            if not city:
                city, region = region, None

            location = _build_location(
                city=city,
                state=region,
                country=payload.get("country_name"),
                country_code=payload.get("country_code"),
                latitude=payload.get("latitude"),
                longitude=payload.get("longitude"),
                source="ip",
            )
        except Exception as exc:  # pragma: no cover - depende de la red externa
            logger.warning("Ubicación por IP no disponible: %s", exc)
            location = _build_location(
                city=None,
                state=None,
                country=None,
                latitude=None,
                longitude=None,
                source="default",
            )

        _ip_cache["data"] = location
        _ip_cache["timestamp"] = now
        return location


def resolve_location(latitude: float | None, longitude: float | None) -> dict:
    """Punto de entrada único para rutas y servicios."""
    if latitude is not None and longitude is not None:
        return resolve_coordinates(latitude, longitude)
    return resolve_ip_location()
