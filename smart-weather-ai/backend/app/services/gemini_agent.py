"""
Agente de razonamiento con Gemini Flash.

El modelo configurado es `gemini-1.5-flash`; si la API ya no lo ofrece, se
resuelve automáticamente el Flash vigente disponible para la clave.

- Inyecta el contexto completo: ciudad, métricas actuales, clasificación de la
  CNN del cielo y pronóstico de lluvia de la LSTM.
- Detecta destinos y normaliza jerga/abreviaciones a topónimos formales con
  Gemini; después geocodifica con sesgo de proximidad y consulta su clima para
  compararlo contra la ubicación actual.
- Usa temperature alta (0.8) y un System Prompt que exige variar el vocabulario
  para evitar respuestas repetitivas.
- Devuelve JSON estricto para alimentar las tarjetas visuales del frontend.
- Si Gemini falla, registra el traceback completo con logger.exception y usa un
  razonador local con múltiples plantillas para no romper la demo.
"""

from __future__ import annotations

import json
import logging
import random
import re
import unicodedata

from app.config import settings
from app.schemas import Recommendations
from app.services import forecast_model, location_service, weather_service

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
Eres "Smart Weather AI", un asistente meteorológico empático, fresco y conversacional.
Recibirás un contexto JSON con la ciudad actual, temperatura, humedad, viento,
análisis visual del cielo (CNN) y pronóstico de lluvia (LSTM). Si el usuario
menciona un destino, el contexto incluirá un bloque "destino" con su clima.

Reglas:
1. Responde en español neutro, en 2 o 3 frases como máximo.
2. Varía tu vocabulario y estructura de oraciones cada vez. Si el usuario te hace
   una pregunta similar, responde con giros lingüísticos distintos pero manteniendo
   la coherencia con los datos meteorológicos.
3. No inventes datos que no estén en el contexto.
4. Deduce recomendaciones prácticas (paraguas, chamarra, protector solar) a partir
   de la temperatura, la humedad, el viento, la CNN y la probabilidad de lluvia.
5. Si "destino" existe y está resuelto, compara explícitamente el clima del destino
   con el actual: temperatura, condición y probabilidad de lluvia. Si no se pudo
   resolver, dilo con naturalidad y no inventes datos de ese lugar.
6. Devuelve EXCLUSIVAMENTE un objeto JSON válido, sin markdown, con esta forma:
{
  "answer": "respuesta natural, cálida y concisa",
  "need_umbrella": true|false,
  "need_jacket": true|false,
  "need_sunscreen": true|false,
  "summary": "recomendación corta de máximo 8 palabras"
}
""".strip()

DESTINATION_PROMPT = """
Detecta si la pregunta del usuario menciona un destino geográfico (ciudad,
colonia, municipio, estado o lugar) cuyo clima quiere consultar o comparar, y
normaliza jerga, abreviaciones o errores de escritura a un topónimo formal de
México.

Reglas:
1. Detecta la intención de viaje o consulta: "voy a...", "iré a...", "me voy
   para...", "qué tal el clima en...", "va a llover en...".
2. Normaliza la jerga a un nombre geográfico formal mexicano. Ejemplos:
   - "huixqui" -> "Huixquilucan, Estado de México"
   - "el tec" -> "Tecnológico de Monterrey Campus Santa Fe"
   - "santa fe" -> "Santa Fe, Ciudad de México"
   - "la condesa" -> "La Condesa, Ciudad de México"
3. Devuelve solo el topónimo normalizado, sin frases como "el clima de".
4. Si hay varios lugares, devuelve únicamente el destino principal.
5. Si no hay un destino explícito, devuelve null.
6. Responde EXCLUSIVAMENTE con JSON válido, sin markdown:
{"destination": "topónimo formal" | null, "is_travel": true|false}
""".strip()

DESTINATION_CONFIG = {
    "temperature": 0.0,
    "max_output_tokens": 80,
    "response_mime_type": "application/json",
}

GENERATION_CONFIG = {
    "temperature": 0.8,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 320,
    "response_mime_type": "application/json",
}

# Orden de preferencia si el modelo configurado ya no está disponible.
# Google retiró gemini-1.5-flash; la app se adapta al flash vigente sin romper.
_FALLBACK_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-flash-lite-latest",
    "gemini-flash-latest",
    "gemini-2.5-flash",
]

_model = None
_model_name: str | None = None
_model_candidates: list[str] = []
_model_index = 0
_model_error: str | None = None


def _list_generate_models(genai) -> list[str]:
    """Nombres de modelos que soportan generateContent."""
    try:
        return [
            model.name.replace("models/", "", 1)
            for model in genai.list_models()
            if "generateContent" in getattr(model, "supported_generation_methods", [])
        ]
    except Exception:
        logger.exception("No se pudieron listar los modelos de Gemini")
        return []


def _version_key(name: str) -> tuple[int, int]:
    match = re.search(r"gemini-(\d+)(?:\.(\d+))?", name)
    if not match:
        return (0, 0)
    return (int(match.group(1)), int(match.group(2) or 0))


def _candidate_model_names(available: list[str]) -> list[str]:
    """Ordena candidatos: configurado, Flash preferidos y versiones recientes."""
    configured = settings.gemini_model

    if not available:
        return [configured, *_FALLBACK_MODELS]

    candidates: list[str] = []
    if configured in available:
        candidates.append(configured)

    for candidate in _FALLBACK_MODELS:
        if candidate in available and candidate not in candidates:
            candidates.append(candidate)

    excluded = ("tts", "image", "transcribe", "preview", "computer", "robotics")
    for name in sorted(available, key=_version_key, reverse=True):
        lowered = name.lower()
        if "flash" not in lowered:
            continue
        if any(token in lowered for token in excluded):
            continue
        if name not in candidates:
            candidates.append(name)

    return candidates[:5] or [configured]


def _build_model(genai, name: str):
    return genai.GenerativeModel(
        model_name=name,
        system_instruction=SYSTEM_PROMPT,
        generation_config=GENERATION_CONFIG,
    )


def _get_model():
    """Inicializa Gemini de forma perezosa y resuelve el modelo vigente."""
    global _model, _model_name, _model_candidates, _model_index, _model_error

    if _model is not None or _model_error is not None:
        return _model

    if not settings.gemini_api_key:
        _model_error = "GEMINI_API_KEY no configurada"
        logger.warning("GEMINI_API_KEY no configurada; se usará el razonador local.")
        return None

    try:
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=settings.gemini_api_key)
        _model_candidates = _candidate_model_names(_list_generate_models(genai))
        _model_index = 0
        _model_name = _model_candidates[0]
        _model = _build_model(genai, _model_name)

        if _model_name != settings.gemini_model:
            logger.warning(
                "El modelo '%s' no está disponible. Usando '%s'.",
                settings.gemini_model,
                _model_name,
            )
        logger.info("Gemini configurado con el modelo %s", _model_name)
        return _model
    except Exception:
        _model_error = "Error inicializando Gemini"
        logger.exception("No se pudo inicializar Gemini")
        return None


def _advance_model() -> bool:
    """Pasa al siguiente modelo candidato cuando el actual falla."""
    global _model, _model_name, _model_index

    if _model_index + 1 >= len(_model_candidates):
        return False

    try:
        import google.generativeai as genai  # type: ignore

        _model_index += 1
        _model_name = _model_candidates[_model_index]
        _model = _build_model(genai, _model_name)
        logger.warning("Reintentando con el modelo %s", _model_name)
        return True
    except Exception:
        logger.exception("No se pudo cambiar al modelo %s", _model_name)
        return False


def _extract_json(text: str) -> dict:
    """Limpia posibles bloques ```json y parsea el primer objeto encontrado."""
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))

    if not isinstance(parsed, dict):
        raise ValueError("Gemini no devolvió un objeto JSON.")
    return parsed


_WEATHER_DESTINATION_PATTERNS = (
    re.compile(
        r"(?:qué|que|cómo|como)\s+(?:está|esta|anda)\s+(?:el\s+)?"
        r"(?:clima|tiempo)\s+(?:en|para|de)\s+(.+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:qué|que|cómo|como)\s+(?:clima|tiempo|temperatura)\s+"
        r"(?:hace|hay|está|esta)\s+(?:en|para)\s+(.+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:clima|tiempo|temperatura|lluvia|lloverá|llovera|llover|llueve|"
        r"pronóstico|pronostico)\s+(?:de|en|para)\s+(.+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:voy|vamos|viajo|viajar|viaje|ir|iré|ire|irme|llegar|llegaré|"
        r"llegare)\s+(?:a|para|hacia)\s+(.+)",
        re.IGNORECASE,
    ),
)

_UPPER_DESTINATION_PATTERN = re.compile(
    r"(?:en|hacia|para)\s+([A-ZÁÉÍÓÚÑ][^,.!?;]{1,60})"
)

_TIME_SUFFIX = re.compile(
    r"\s+(?:hoy|mañana|pasado\s+mañana|esta\s+(?:tarde|noche|mañana|semana)|"
    r"este\s+(?:fin|sábado|sabado|domingo)|el\s+(?:fin|sábado|sabado|domingo)|"
    r"la\s+(?:próxima|proxima)\s+semana|por\s+la\s+(?:mañana|tarde|noche)|"
    r"ahora|pronto|después|despues)\b.*$",
    re.IGNORECASE,
)


def _clean_destination(candidate: str | None) -> str | None:
    text = (candidate or "").strip(" \t\n\r,.;:!?¡¿\"'")
    text = re.split(r"[,;]", text, maxsplit=1)[0]
    text = _TIME_SUFFIX.sub("", text)
    text = re.sub(
        r"^(?:viajar|viaje|ir|irme|llegar|salir)\s+(?:a|para|hacia)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.split(
        r"\s+(?:y\s+)?(?:va|van|voy|vamos)\s+a\s+|\s+(?:lloverá|llovera|llueve)\b",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    text = re.split(r"\s+(?:y|pero|aunque|porque)\s+", text, maxsplit=1, flags=re.IGNORECASE)[0]
    text = re.sub(r"\s+(?:para|en|de|a|hacia)\s*$", "", text, flags=re.IGNORECASE)
    text = text.strip(" \t\n\r,.;:!?¡¿\"'")

    if not text or len(text) > 80:
        return None
    if text.lower() in {
        "el clima",
        "el tiempo",
        "la ciudad",
        "mi casa",
        "casa",
        "trabajo",
        "aquí",
        "aqui",
    }:
        return None
    return text


def _destination_from_text(user_prompt: str) -> str | None:
    for pattern in _WEATHER_DESTINATION_PATTERNS:
        match = pattern.search(user_prompt)
        if match:
            destination = _clean_destination(match.group(1))
            if destination:
                return destination

    match = _UPPER_DESTINATION_PATTERN.search(user_prompt)
    if match:
        return _clean_destination(match.group(1))
    return None


def _extract_destination_with_gemini(user_prompt: str) -> str | None:
    if _get_model() is None:
        return None

    try:
        import google.generativeai as genai  # type: ignore

        extractor = genai.GenerativeModel(
            model_name=_model_name or settings.gemini_model,
            system_instruction=DESTINATION_PROMPT,
            generation_config=DESTINATION_CONFIG,
        )
        response = extractor.generate_content(
            f"Pregunta: {user_prompt}",
            request_options={"timeout": 15},
        )
        parsed = _extract_json(response.text)
        destination = parsed.get("destination")
        if isinstance(destination, str):
            normalized = _clean_destination(destination)
            if normalized:
                logger.info(
                    "Gemini normalizó el destino a '%s' (viaje=%s)",
                    normalized,
                    bool(parsed.get("is_travel")),
                )
            return normalized
    except Exception:
        logger.exception("No se pudo extraer el destino con Gemini")
    return None


_DESTINATION_STOPWORDS = {
    "de",
    "del",
    "la",
    "las",
    "el",
    "los",
    "y",
    "en",
    "con",
    "por",
    "para",
    "que",
}


def _tokenize(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", (text or "").lower())
    plain = "".join(char for char in normalized if not unicodedata.combining(char))
    return [token for token in re.split(r"[^a-z0-9]+", plain) if token]


def _destination_matches_prompt(destination: str, user_prompt: str) -> bool:
    """Evita que Gemini invente destinos que el usuario no mencionó."""
    prompt_tokens = _tokenize(user_prompt)
    if not prompt_tokens:
        return False

    for token in _tokenize(destination):
        if len(token) < 3 or token in _DESTINATION_STOPWORDS:
            continue
        for prompt_token in prompt_tokens:
            if len(prompt_token) < 3:
                continue
            if token.startswith(prompt_token) or prompt_token.startswith(token):
                return True
    return False


def _extract_destination(user_prompt: str) -> str | None:
    # Gemini entiende jerga, abreviaciones e intención de viaje; el regex queda
    # solo como respaldo cuando no hay clave/modelo disponible.
    normalized = _extract_destination_with_gemini(user_prompt)
    if normalized:
        if _destination_matches_prompt(normalized, user_prompt):
            return normalized
        logger.info(
            "Destino '%s' descartado: no aparece en la pregunta '%s'",
            normalized,
            user_prompt,
        )
    return _destination_from_text(user_prompt)


def _optional_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_destination(user_prompt: str, context_data: dict) -> dict | None:
    place = _extract_destination(user_prompt)
    if not place:
        return None

    current = context_data.get("current") or {}
    user_lat = _optional_float(current.get("latitude"))
    user_lon = _optional_float(current.get("longitude"))

    logger.info("Destino detectado en la pregunta: '%s'", place)
    location = location_service.geocode_destination(place, user_lat, user_lon)

    if (
        not location
        or location.get("latitude") is None
        or location.get("longitude") is None
    ):
        logger.info("Destino '%s' sin coordenadas válidas", place)
        return {"query": place, "resolved": False}

    logger.info(
        "Destino '%s' geocodificado: %s (%.5f, %.5f)",
        place,
        location.get("display_name"),
        location["latitude"],
        location["longitude"],
    )
    destination_current = weather_service.get_weather_for_destination(location)
    destination_forecast = forecast_model.generate_forecast(destination_current)
    destination = {
        "query": place,
        "resolved": True,
        "location": location,
        "current": destination_current,
        "forecast": destination_forecast,
    }
    next_hours_rain = max(
        _max_rain_probability(destination),
        int(destination_current.get("rain_probability") or 0),
    )
    logger.info(
        "Clima destino '%s': %.1f°C, lluvia actual %s%%, próximas horas %s%%, %s",
        location.get("display_name"),
        float(destination_current.get("temperature") or 0),
        destination_current.get("rain_probability"),
        next_hours_rain,
        destination_current.get("condition"),
    )
    return destination


def _max_rain_probability(context_data: dict) -> int:
    forecast = context_data.get("forecast") or {}
    points = forecast.get("points") if isinstance(forecast, dict) else None
    if not points:
        return 0
    try:
        return max(int(p.get("rain_probability", 0)) for p in points)
    except (TypeError, ValueError):
        return 0


def _destination_data_block(destination: dict) -> str | None:
    if not destination.get("resolved"):
        return None

    current = destination.get("current") or {}
    name = current.get("location") or destination.get("query") or "Destino"
    temperature = _optional_float(current.get("temperature"))
    current_rain = int(current.get("rain_probability") or 0)
    rain = max(_max_rain_probability(destination), current_rain)
    condition = current.get("condition") or "Condición no disponible"
    temperature_text = (
        f"{temperature:.1f}".rstrip("0").rstrip(".")
        if temperature is not None
        else "N/D"
    )
    return (
        f"[DATOS DESTINO ({name})]:\n"
        f"Temperatura: {temperature_text}°C, Lluvia máx: {rain}%, Condición: {condition}"
    )


def _build_gemini_context(context_data: dict) -> dict:
    """Resumen legible que garantiza que Gemini reciba todos los datos clave."""
    current = context_data.get("current") or {}
    vision = context_data.get("vision") or {}
    forecast = context_data.get("forecast") or {}
    points = forecast.get("points") if isinstance(forecast, dict) else []
    destination = context_data.get("destination") or {}
    destination_block = _destination_data_block(destination)

    destination_context = None
    if destination:
        destination_current = destination.get("current") or {}
        destination_context = {
            "consulta": destination.get("query"),
            "resuelto": bool(destination.get("resolved")),
        }
        if destination.get("resolved"):
            destination_context.update(
                {
                    "ciudad": destination_current.get(
                        "location", "Ubicación no disponible"
                    ),
                    "temperatura_c": destination_current.get("temperature"),
                    "sensacion_c": destination_current.get("feels_like"),
                    "humedad_pct": destination_current.get("humidity"),
                    "viento_kmh": destination_current.get("wind_kph"),
                    "condicion": destination_current.get("condition"),
                    "estado_cielo": destination_current.get("sky_state"),
                    "lluvia_actual_pct": destination_current.get("rain_probability"),
                    "lluvia_maxima_pct": _max_rain_probability(destination),
                }
            )

    return {
        "ciudad": current.get("location", "Ubicación no disponible"),
        "temperatura_c": current.get("temperature"),
        "sensacion_c": current.get("feels_like"),
        "humedad_pct": current.get("humidity"),
        "viento_kmh": current.get("wind_kph"),
        "condicion": current.get("condition"),
        "estado_cielo": current.get("sky_state"),
        "lluvia_actual_pct": current.get("rain_probability"),
        "vision_cnn": {
            "etiqueta": vision.get("label"),
            "estado": vision.get("state"),
            "confianza": vision.get("confidence"),
        },
        "pronostico_lstm": {
            "lluvia_maxima_pct": _max_rain_probability(context_data),
            "horas": points,
        },
        "destino": destination_context,
        "datos_destino_texto": destination_block,
    }


def _recommendation_key(
    *,
    rain_probability: int,
    humidity: int,
    temperature: float,
    wind: float,
    condition: str,
    vision_state: str,
) -> str:
    need_umbrella = (
        rain_probability >= 40
        or "lluvia" in vision_state
        or "lluvia" in condition.lower()
        or humidity >= 80
    )
    need_jacket = temperature <= 18 or wind >= 25
    need_sunscreen = (
        temperature >= 26
        and rain_probability < 30
        and "lluvia" not in vision_state
        and "lluvia" not in condition.lower()
    )

    if need_umbrella:
        return "umbrella"
    if need_jacket:
        return "jacket"
    if need_sunscreen:
        return "sunscreen"
    return "none"


def _fallback_response(user_prompt: str, context_data: dict) -> dict:
    """
    Razonador local con plantillas variadas.

    Mantiene el mismo contrato que Gemini y evita repetir exactamente la misma
    frase cuando la API no está disponible o no hay clave configurada.
    """
    current = context_data.get("current") or {}
    vision = context_data.get("vision") or {}
    destination = context_data.get("destination") or {}
    destination_current = destination.get("current") or {}

    city = str(current.get("location", "tu zona"))
    temperature = float(current.get("temperature", 23))
    humidity = int(current.get("humidity", 60))
    wind = float(current.get("wind_kph", 10))
    condition = str(current.get("condition", "despejado"))
    vision_state = str(vision.get("state", "")).lower()
    rain_prob = _max_rain_probability(context_data)

    key = _recommendation_key(
        rain_probability=rain_prob,
        humidity=humidity,
        temperature=temperature,
        wind=wind,
        condition=condition,
        vision_state=vision_state,
    )
    need_umbrella = key == "umbrella"
    need_jacket = key == "jacket"
    need_sunscreen = key == "sunscreen"

    summaries = {
        "umbrella": [
            "Lleva paraguas, mejor prevenir",
            "No olvides el paraguas",
            "Un paraguas te vendrá bien",
        ],
        "jacket": [
            "Usa una chamarra ligera",
            "Considera una chamarra",
            "Abrígate un poco",
        ],
        "sunscreen": [
            "Aplica protector solar",
            "No olvides el bloqueador",
            "Protector solar recomendado",
        ],
        "none": [
            "Día agradable, disfrútalo",
            "Clima estable, sal sin preocupación",
            "Buen día para estar fuera",
        ],
    }

    summary = random.choice(summaries[key])

    openings = [
        f"En {city} tenemos {temperature:.0f}°C y {condition.lower()}.",
        f"Ahora mismo el termómetro marca {temperature:.0f}°C en {city}, con {condition.lower()}.",
        f"Por aquí, en {city}, hay {temperature:.0f}°C y cielo {condition.lower()}.",
    ]

    if destination.get("resolved"):
        destination_city = str(destination_current.get("location", destination.get("query")))
        destination_temperature = float(
            destination_current.get("temperature", temperature)
        )
        destination_humidity = int(destination_current.get("humidity", humidity))
        destination_wind = float(destination_current.get("wind_kph", wind))
        destination_condition = str(destination_current.get("condition", condition))
        destination_rain = _max_rain_probability(destination)
        destination_key = _recommendation_key(
            rain_probability=destination_rain,
            humidity=destination_humidity,
            temperature=destination_temperature,
            wind=destination_wind,
            condition=destination_condition,
            vision_state="",
        )
        destination_summary = random.choice(summaries[destination_key])

        comparisons = [
            (
                f"En {city} tienes {temperature:.0f}°C y {condition.lower()}, "
                f"mientras que en {destination_city} hay {destination_temperature:.0f}°C "
                f"con {destination_condition.lower()}."
            ),
            (
                f"Tu zona marca {temperature:.0f}°C y {condition.lower()}; "
                f"{destination_city} está en {destination_temperature:.0f}°C "
                f"con {destination_condition.lower()}."
            ),
            (
                f"La diferencia es clara: {temperature:.0f}°C y {condition.lower()} en {city}, "
                f"frente a {destination_temperature:.0f}°C y "
                f"{destination_condition.lower()} en {destination_city}."
            ),
        ]

        rain_difference = destination_rain - rain_prob
        if rain_difference >= 15:
            rain_lines = [
                (
                    f"Allá la probabilidad de lluvia es mayor "
                    f"({destination_rain}% frente a {rain_prob}% aquí)."
                ),
                (
                    f"En {destination_city} hay más riesgo de lluvia: "
                    f"{destination_rain}% contra {rain_prob}% en tu ubicación."
                ),
            ]
        elif rain_difference <= -15:
            rain_lines = [
                (
                    f"La lluvia se ve más probable en tu zona "
                    f"({rain_prob}% frente a {destination_rain}% allá)."
                ),
                (
                    f"En {destination_city} el riesgo de lluvia es menor: "
                    f"{destination_rain}% contra {rain_prob}% aquí."
                ),
            ]
        else:
            rain_lines = [
                (
                    f"La probabilidad de lluvia es parecida: "
                    f"{rain_prob}% aquí y {destination_rain}% allá."
                ),
                (
                    f"En lluvia no hay gran diferencia: "
                    f"{destination_rain}% en {destination_city} y {rain_prob}% en {city}."
                ),
            ]

        closings = [
            f"Si tu plan es para {destination_city}, {destination_summary.lower()}.",
            f"Para {destination_city}, {destination_summary.lower()}.",
            f"En resumen, {destination_summary.lower()} si vas a {destination_city}.",
        ]
        answer = f"{random.choice(comparisons)} {random.choice(rain_lines)} {random.choice(closings)}"
    elif destination:
        destination_query = str(destination.get("query") or "ese destino")
        answer = (
            f"{random.choice(openings)} No pude ubicar \"{destination_query}\" con certeza, "
            "así que revisa el nombre o agrega la ciudad/estado. "
            f"Para tu ubicación actual, {summary.lower()}."
        )
    else:
        if key == "umbrella":
            details = [
                f"Con {rain_prob}% de lluvia en el horizonte y {humidity}% de humedad, {summary.lower()}.",
                f"El pronóstico apunta a un {rain_prob}% de probabilidad de lluvia, así que {summary.lower()}.",
                f"La humedad ronda el {humidity}% y la lluvia podría aparecer; {summary.lower()}.",
            ]
        elif key == "jacket":
            details = [
                f"La sensación es fresca y el viento sopla a {wind:.0f} km/h; {summary.lower()}.",
                f"Con {wind:.0f} km/h de viento, {summary.lower()}.",
                f"Las condiciones invitan a abrigarse; {summary.lower()}.",
            ]
        elif key == "sunscreen":
            details = [
                f"El ambiente está cálido y la lluvia se ve lejana; {summary.lower()}.",
                f"Con {temperature:.0f}°C y pocas nubes de lluvia, {summary.lower()}.",
                f"Hoy conviene cuidar la piel; {summary.lower()}.",
            ]
        else:
            details = [
                f"El clima se mantiene estable y sin cambios importantes; {summary.lower()}.",
                f"Las condiciones son tranquilas; {summary.lower()}.",
                f"No se esperan sorpresas del tiempo; {summary.lower()}.",
            ]

        closings = [
            f"Para tu pregunta sobre \"{user_prompt[:80]}\", eso es lo que te recomiendo.",
            f"Y respondiendo a \"{user_prompt[:80]}\": {summary.lower()}.",
            f"En resumen, {summary.lower()}.",
        ]

        answer = f"{random.choice(openings)} {random.choice(details)} {random.choice(closings)}"

    return {
        "answer": answer,
        "need_umbrella": need_umbrella,
        "need_jacket": need_jacket,
        "need_sunscreen": need_sunscreen,
        "summary": summary,
        "source": "fallback",
    }


def generate_weather_response(user_prompt: str, context_data: dict) -> dict:
    """
    Orquesta la consulta al agente.

    Retorna:
        {
          "answer": str,
          "recommendations": Recommendations,
          "source": "gemini" | "fallback"
        }
    """
    destination = _resolve_destination(user_prompt, context_data)
    if destination:
        context_data = {**context_data, "destination": destination}

    model = _get_model()
    gemini_context = _build_gemini_context(context_data)

    if model is not None:
        destination_block = gemini_context.get("datos_destino_texto")
        if destination_block:
            logger.info("Datos destino enviados a Gemini:\n%s", destination_block)
        prompt = (
            f"{destination_block}\n\n" if destination_block else ""
        ) + (
            "Contexto meteorológico actual (JSON):\n"
            f"{json.dumps(gemini_context, ensure_ascii=False)}\n\n"
            f"Pregunta del usuario: {user_prompt}\n\n"
            "Responde con naturalidad, sin frases hechas y variando la redacción. "
            "Si hay un destino resuelto, compara ambos climas en la misma respuesta. "
            "Devuelve únicamente el JSON solicitado."
        )

        while model is not None:
            try:
                response = model.generate_content(
                    prompt,
                    request_options={"timeout": 25},
                )
                parsed = _extract_json(response.text)
                answer = str(parsed.get("answer", "")).strip()

                if not answer:
                    raise ValueError("Gemini devolvió una respuesta vacía.")

                recommendations = Recommendations(
                    need_umbrella=bool(parsed.get("need_umbrella", False)),
                    need_jacket=bool(parsed.get("need_jacket", False)),
                    need_sunscreen=bool(parsed.get("need_sunscreen", False)),
                    summary=str(parsed.get("summary", ""))[:80],
                )
                return {
                    "answer": answer,
                    "recommendations": recommendations,
                    "source": "gemini",
                    "destination": destination,
                }
            except Exception:
                # Traceback completo visible en consola para depurar cuota, red o JSON.
                logger.exception("Error llamando a Gemini")
                if not _advance_model():
                    break
                model = _model

    fallback = _fallback_response(user_prompt, context_data)
    return {
        "answer": fallback["answer"],
        "recommendations": Recommendations(
            need_umbrella=fallback["need_umbrella"],
            need_jacket=fallback["need_jacket"],
            need_sunscreen=fallback["need_sunscreen"],
            summary=fallback["summary"],
        ),
        "source": "fallback",
        "destination": destination,
    }
