"""
Resolución de ubicación para Smart Weather AI.

Prioridad:
1. Coordenadas GPS enviadas por el cliente -> geocodificación inversa (Nominatim).
2. Sin coordenadas -> ubicación aproximada por IP pública (ipapi.co).
3. Si ambos fallan -> etiqueta neutra para no romper la app.

Geocodificación de destinos:
1. Hotspots locales (coordenadas fijas para colonias/zona conurbadas).
2. Nominatim restringido a México.
3. Open-Meteo Geocoding como respaldo.

Los resultados se cachean para respetar las políticas de uso de los servicios
gratuitos y para que las llamadas simultáneas de clima + pronóstico no dupliquen
peticiones externas.
"""

from __future__ import annotations

import logging
import re
import threading
import time
import unicodedata
from functools import lru_cache
from typing import Any

import requests

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
OPEN_METEO_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
IPAPI_URL = "https://ipapi.co/json/"
USER_AGENT = "SmartWeatherAI-App/1.0"
REQUEST_TIMEOUT = 4
IP_CACHE_TTL = 600  # 10 minutos
SEARCH_VIEWBOX_SPAN = 1.25
MEXICO_BBOX = (-118.5, 14.5, -86.5, 32.8)

# Nivel 1: coordenadas fijas para zonas que los geocodificadores globales
# suelen confundir con municipios homónimos de otros estados/países.
KNOWN_HOTSPOTS: dict[str, dict[str, Any]] = {
    "interlomas": {
        "name": "Interlomas (Huixquilucan)",
        "lat": 19.3986,
        "lon": -99.2831,
        "state": "Estado de México",
    },
    "santa fe": {
        "name": "Santa Fe (CDMX)",
        "lat": 19.3598,
        "lon": -99.2589,
        "state": "Ciudad de México",
    },
    "polanco": {
        "name": "Polanco (CDMX)",
        "lat": 19.4337,
        "lon": -99.1917,
        "state": "Ciudad de México",
    },
    "bosques de las lomas": {
        "name": "Bosques de las Lomas",
        "lat": 19.3942,
        "lon": -99.2458,
        "state": "Ciudad de México",
    },
    "condesa": {
        "name": "La Condesa (CDMX)",
        "lat": 19.4115,
        "lon": -99.1717,
        "state": "Ciudad de México",
    },
    "roma": {
        "name": "Colonia Roma (CDMX)",
        "lat": 19.4184,
        "lon": -99.1622,
        "state": "Ciudad de México",
    },
    "coyoacan": {
        "name": "Coyoacán",
        "lat": 19.3499,
        "lon": -99.1623,
        "state": "Ciudad de México",
    },
    "satelite": {
        "name": "Ciudad Satélite (Naucalpan)",
        "lat": 19.5100,
        "lon": -99.2344,
        "state": "Estado de México",
    },
    "naucalpan": {
        "name": "Naucalpan de Juárez",
        "lat": 19.4785,
        "lon": -99.2396,
        "state": "Estado de México",
    },
    "cuernavaca": {
        "name": "Cuernavaca",
        "lat": 18.9242,
        "lon": -99.2216,
        "state": "Morelos",
    },
}

# Abreviaturas de estados de México para un Header más compacto.
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


def _hotspot_key(value: str) -> str:
    normalized = _normalize_text(value)
    normalized = re.sub(r"\b(?:colonia|col|la|el)\b", " ", normalized)
    normalized = normalized.replace("ciudad de mexico", " ").replace("cdmx", " ")
    return " ".join(normalized.replace(",", " ").split())


def _find_hotspot(query: str) -> dict[str, Any] | None:
    key = _hotspot_key(query)
    if key in KNOWN_HOTSPOTS:
        return KNOWN_HOTSPOTS[key]
    for hotspot_key, hotspot in KNOWN_HOTSPOTS.items():
        if key.startswith(f"{hotspot_key} "):
            return hotspot
    return None


def _hotspot_location(hotspot: dict[str, Any]) -> dict:
    return {
        "display_name": hotspot["name"],
        "city": hotspot["name"],
        "state": hotspot["state"],
        "country": "México",
        "country_code": "mx",
        "latitude": hotspot["lat"],
        "longitude": hotspot["lon"],
        "source": "hotspot",
    }


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


def geocode_destination(destination_name: str) -> dict | None:
    """
    Geocodifica un destino en tres niveles:
    1. Hotspot local (sin latencia ni APIs).
    2. Nominatim restringido a México.
    3. Open-Meteo Geocoding como respaldo.
    """
    query = (destination_name or "").strip()
    if not query:
        return None

    logger.info("Resolviendo destino '%s'", query)

    hotspot = _find_hotspot(query)
    if hotspot:
        location = _hotspot_location(hotspot)
        logger.info(
            "Nivel 1 hotspot local: '%s' -> %s (%.5f, %.5f)",
            query,
            location["display_name"],
            location["latitude"],
            location["longitude"],
        )
        return location

    for candidate in _nominatim_destination_queries(query):
        try:
            with _search_lock:
                location = _geocode_place_cached(candidate, None, None, "mx")
            if location:
                logger.info(
                    "Nivel 2 Nominatim: '%s' -> %s",
                    query,
                    location.get("display_name"),
                )
                return location
        except requests.Timeout as exc:
            logger.warning("Nominatim timeout para '%s': %s", candidate, exc)
            break
        except Exception as exc:  # pragma: no cover - depende de la red externa
            logger.warning("Nominatim falló para '%s': %s", candidate, exc)

    for candidate in _open_meteo_destination_queries(query):
        try:
            location = _open_meteo_geocode_cached(candidate)
            if location:
                logger.info(
                    "Nivel 3 Open-Meteo: '%s' -> %s",
                    query,
                    location.get("display_name"),
                )
                return location
        except requests.Timeout as exc:
            logger.warning("Open-Meteo timeout para '%s': %s", candidate, exc)
            break
        except Exception as exc:  # pragma: no cover - depende de la red externa
            logger.warning("Open-Meteo Geocoding falló para '%s': %s", candidate, exc)

    logger.info("No se pudo geocodificar el destino '%s'", query)
    return None


def geocode_place(
    place_name: str,
    *,
    near_latitude: float | None = None,
    near_longitude: float | None = None,
    country_code: str | None = None,
) -> dict | None:
    """Compatibilidad con llamadas previas; delega en geocode_destination."""
    return geocode_destination(place_name)


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
