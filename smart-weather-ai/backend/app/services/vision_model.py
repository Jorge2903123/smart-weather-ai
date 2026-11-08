"""
Clasificador de imágenes del cielo (CNN).

Flujo:
1. Recibe los bytes de la imagen enviada por el cliente.
2. Preprocesa: redimensiona a 224x224 y normaliza con la media/desviación de
   ImageNet (formato esperado por la mayoría de CNNs preentrenadas).
3. Si existe un modelo entrenado en `VISION_MODEL_PATH`, lo usa.
4. Si no existe (o falla la carga), aplica un clasificador heurístico basado en
   estadísticas de color/brillo. Así el endpoint queda 100% funcional desde el
   primer arranque, mientras se entrena y conecta la CNN definitiva.

Para conectar los pesos reales basta con guardar un modelo PyTorch en la ruta
indicada y adaptar `_load_model`. El contrato de salida no cambia.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError

from app.config import settings

logger = logging.getLogger(__name__)

IMAGE_SIZE = (224, 224)
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# Umbrales de calidad. Una foto con lente tapado, negra o de color plano no
# contiene información suficiente para clasificar el cielo y no debe arrojar
# falsos positivos de lluvia.
MIN_BRIGHTNESS = 25.0  # media en escala de grises (0-255)
MIN_VARIANCE = 12.0  # varianza en escala de grises (0-65025)

INVALID_IMAGE_STATUS = "invalid_image"
INTERIOR_LABEL = "Interior o superficie plana detectada"
INTERIOR_MESSAGE = (
    "No se detectó cielo abierto. Por favor apunta hacia el exterior."
)
INVALID_IMAGE_DESCRIPTION = (
    "Imagen no válida o demasiado oscura. Por favor apunta hacia el cielo abierto."
)

# Umbrales del filtro cromático/textural que separa cielo de interiores.
BLUE_HUE_MIN = 0.50
BLUE_HUE_MAX = 0.74
MIN_BLUE_SKY_FRACTION = 0.10
MIN_COOL_BIAS_FRACTION = 0.20
MIN_NEUTRAL_CLOUD_FRACTION = 0.55
MIN_NEUTRAL_CLOUD_GRADIENT_STD = 1.5
MIN_NATURAL_VERTICAL_DELTA = 0.12
MAX_NEUTRAL_COLOR_STD = 0.09
MIN_WARM_SKY_FRACTION = 0.35
MIN_WARM_SKY_GRADIENT_STD = 2.0
MIN_WARM_SKY_COLOR_STD = 0.08
MAX_WARM_SKY_EDGE_DENSITY = 0.06
FLAT_NEUTRAL_FRACTION = 0.65
MAX_FLAT_GRADIENT_STD = 1.0
MAX_FLAT_COLOR_STD = 0.05

# Etiquetas de salida de la CNN (orden estable para mapear índices del modelo).
CLASS_LABELS = [
    ("Cielo despejado", "Soleado"),
    ("Parcialmente nublado", "Nublado"),
    ("Nubes densas", "Posible lluvia"),
    ("Tormenta", "Alerta de lluvia"),
    ("Niebla", "Visibilidad reducida"),
]

# Probabilidad de lluvia base (0-100) asociada a cada etiqueta.
_LABEL_RAIN_PROBABILITY = {
    "Cielo despejado": 0.0,
    "Parcialmente nublado": 15.0,
    "Nubes densas": 55.0,
    "Tormenta": 85.0,
    "Niebla": 10.0,
}

_LABEL_DESCRIPTIONS = {
    "Cielo despejado": "El cielo se ve despejado y luminoso.",
    "Parcialmente nublado": "Hay nubes dispersas con zonas de cielo abierto.",
    "Nubes densas": "Las nubes cubren la mayor parte del cielo.",
    "Tormenta": "El cielo está muy oscuro, compatible con una tormenta.",
    "Niebla": "La visibilidad parece reducida por niebla o bruma.",
}


def _load_rgb_image(image_bytes: bytes) -> Image.Image:
    """Decodifica los bytes recibidos y valida que sea una imagen real."""
    try:
        return Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("El archivo recibido no es una imagen válida.") from exc


def _image_statistics(image: Image.Image) -> tuple[float, float]:
    """Devuelve (brillo medio, varianza) en escala de grises (0-255)."""
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    return float(gray.mean()), float(gray.var())


def _is_valid_sky_image(brightness: float, variance: float) -> bool:
    return brightness >= MIN_BRIGHTNESS and variance >= MIN_VARIANCE


def _scene_features(image: Image.Image) -> dict[str, float]:
    """
    Extrae señales cromáticas y de textura para distinguir cielo de interiores.

    - HSV: azul atmosférico, sesgo frío (B > R) y tonos cálidos de luz artificial.
    - Gradientes: una superficie plana (techo/pared) tiene poca dispersión;
      las nubes producen transiciones suaves pero variables.
    - Gradiente vertical: el cielo suele tener una transición natural arriba/abajo.
    """
    resized = image.resize((128, 128), Image.Resampling.BILINEAR)
    rgb = np.asarray(resized, dtype=np.float32) / 255.0
    hsv = np.asarray(resized.convert("HSV"), dtype=np.float32) / 255.0
    hue, saturation, value = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    red, green, blue = rgb[..., 0], rgb[..., 1], rgb[..., 2]

    gray = np.asarray(resized.convert("L"), dtype=np.float32)
    gradient_y, gradient_x = np.gradient(gray)
    gradient_magnitude = np.hypot(gradient_x, gradient_y)

    blue_sky_fraction = float(
        (
            (hue >= BLUE_HUE_MIN)
            & (hue <= BLUE_HUE_MAX)
            & (saturation >= 0.10)
            & (value >= 0.22)
        ).mean()
    )
    cool_bias_fraction = float(
        (((blue - red) > 0.04) & ((blue - green) > -0.02) & (value > 0.18)).mean()
    )
    warm_fraction = float(
        (
            ((hue < 0.14) | (hue > 0.92))
            & (saturation > 0.12)
            & (value > 0.20)
        ).mean()
    )
    neutral_fraction = float((saturation < 0.12).mean())
    vertical_delta = float(
        abs(value[:42].mean() - value[86:].mean())
    )

    return {
        "blue_sky_fraction": blue_sky_fraction,
        "cool_bias_fraction": cool_bias_fraction,
        "warm_fraction": warm_fraction,
        "neutral_fraction": neutral_fraction,
        "vertical_delta": vertical_delta,
        "gradient_mean": float(gradient_magnitude.mean()),
        "gradient_std": float(gradient_magnitude.std()),
        "edge_density": float((gradient_magnitude > 8.0).mean()),
        "color_std": float(rgb.std(axis=(0, 1)).mean()),
    }


def _looks_like_interior(features: dict[str, float]) -> bool:
    """Decide si la escena carece de señales atmosféricas de cielo abierto."""
    has_atmospheric_color = (
        features["blue_sky_fraction"] >= MIN_BLUE_SKY_FRACTION
        or features["cool_bias_fraction"] >= MIN_COOL_BIAS_FRACTION
    )
    if has_atmospheric_color:
        return False

    flat_neutral_surface = (
        features["neutral_fraction"] >= FLAT_NEUTRAL_FRACTION
        and features["gradient_std"] < MAX_FLAT_GRADIENT_STD
        and features["color_std"] < MAX_FLAT_COLOR_STD
    )
    if flat_neutral_surface:
        return True

    # Cielo cubierto neutro: gradiente vertical natural + textura suave de nubes.
    neutral_cloud_sky = (
        features["neutral_fraction"] >= MIN_NEUTRAL_CLOUD_FRACTION
        and features["vertical_delta"] >= MIN_NATURAL_VERTICAL_DELTA
        and features["gradient_std"] >= MIN_NEUTRAL_CLOUD_GRADIENT_STD
        and features["color_std"] <= MAX_NEUTRAL_COLOR_STD
        and features["edge_density"] <= 0.12
    )

    # Amanecer/atardecer: tonos cálidos pero con gradiente amplio y textura.
    warm_sky = (
        features["warm_fraction"] >= MIN_WARM_SKY_FRACTION
        and features["vertical_delta"] >= MIN_NATURAL_VERTICAL_DELTA
        and features["gradient_std"] >= MIN_WARM_SKY_GRADIENT_STD
        and features["color_std"] >= MIN_WARM_SKY_COLOR_STD
        and features["edge_density"] <= MAX_WARM_SKY_EDGE_DENSITY
    )

    return not (neutral_cloud_sky or warm_sky)


def _enrich_result(result: dict) -> dict:
    """Agrega estado, descripción y probabilidad de lluvia al resultado."""
    label = result.get("label", "Condición variable")
    confidence = float(result.get("confidence") or 0.0)
    base_rain = _LABEL_RAIN_PROBABILITY.get(label, 30.0)
    description = _LABEL_DESCRIPTIONS.get(label, "Análisis del cielo completado.")
    return {
        **result,
        "status": "ok",
        "description": description,
        "rain_probability": round(base_rain * confidence, 1),
        "has_image": True,
        "is_valid": True,
        "sky_label": label,
        "message": description,
    }


def _invalid_result(message: str = INVALID_IMAGE_DESCRIPTION, label: str = "Imagen no válida") -> dict:
    return {
        "label": label,
        "confidence": 0.0,
        "state": label,
        "source": "heuristic",
        "status": INVALID_IMAGE_STATUS,
        "description": message,
        "rain_probability": 0.0,
        "has_image": True,
        "is_valid": False,
        "sky_label": label,
        "message": message,
    }


def _interior_result() -> dict:
    return _invalid_result(message=INTERIOR_MESSAGE, label=INTERIOR_LABEL)


def preprocess_image(image_bytes: bytes) -> np.ndarray:
    """Convierte bytes en un tensor RGB 224x224x3 normalizado (NHWC)."""
    image = _load_rgb_image(image_bytes)
    image = image.resize(IMAGE_SIZE, Image.Resampling.BILINEAR)
    array = np.asarray(image, dtype=np.float32) / 255.0
    array = (array - IMAGENET_MEAN) / IMAGENET_STD
    return array


def _load_model():
    """
    Carga opcional del modelo de visión.

    Se importa PyTorch de forma perezosa para no hacerlo obligatorio en el
    entorno de desarrollo. Reemplaza el `torch.load` por la arquitectura usada
    al entrenar (ResNet, MobileNet, EfficientNet, etc.).
    """
    model_path = settings.vision_model_path
    if not model_path or not Path(model_path).exists():
        return None

    try:
        import torch  # type: ignore

        model = torch.load(model_path, map_location="cpu")
        model.eval()
        logger.info("Modelo de visión cargado desde %s", model_path)
        return model
    except Exception as exc:  # pragma: no cover - depende del entorno
        logger.warning("No se pudo cargar el modelo de visión: %s", exc)
        return None


_MODEL = _load_model()


def _infer_with_model(image_array: np.ndarray) -> dict | None:
    """Inferencia real cuando hay pesos disponibles. Ajustar según el modelo."""
    if _MODEL is None:
        return None

    try:
        import torch  # type: ignore

        # NHWC -> NCHW
        tensor = torch.from_numpy(image_array).permute(2, 0, 1).unsqueeze(0)
        with torch.no_grad():
            logits = _MODEL(tensor)
            probs = torch.softmax(logits, dim=1)[0]
        index = int(torch.argmax(probs).item())
        label, state = CLASS_LABELS[index]
        return _enrich_result(
            {
                "label": label,
                "confidence": round(float(probs[index].item()), 2),
                "state": state,
                "source": "cnn",
            }
        )
    except Exception as exc:  # pragma: no cover - depende del entorno
        logger.warning("Fallo la inferencia CNN, usando respaldo: %s", exc)
        return None


def _heuristic_analysis(image: Image.Image) -> dict:
    """
    Clasificador de respaldo basado en brillo, dominancia de azul y contraste.

    No pretende sustituir a la CNN: entrega resultados plausibles y estables
    para que la demo funcione sin pesos entrenados.
    """
    resized = image.resize((64, 64), Image.Resampling.BILINEAR)
    pixels = np.asarray(resized, dtype=np.float32)

    red = pixels[:, :, 0].mean()
    green = pixels[:, :, 1].mean()
    blue = pixels[:, :, 2].mean()
    brightness = pixels.mean()
    contrast = pixels.std()
    blue_dominance = blue - (red + green) / 2

    if brightness < 75:
        label, state, confidence = "Tormenta", "Alerta de lluvia", 0.91
    elif brightness < 120 and contrast > 45:
        label, state, confidence = "Nubes densas", "Posible lluvia", 0.87
    elif blue_dominance > 18 and brightness > 150:
        label, state, confidence = "Cielo despejado", "Soleado", 0.93
    elif blue_dominance > 5:
        label, state, confidence = "Parcialmente nublado", "Nublado", 0.82
    elif contrast < 18:
        label, state, confidence = "Niebla", "Visibilidad reducida", 0.76
    else:
        label, state, confidence = "Nubes densas", "Posible lluvia", 0.80

    return _enrich_result(
        {
            "label": label,
            "confidence": confidence,
            "state": state,
            "source": "heuristic",
        }
    )


def analyze_sky_image(image_bytes: bytes) -> dict:
    """Punto de entrada del servicio de visión."""
    if not image_bytes:
        raise ValueError("La imagen está vacía.")

    # Decodifica una sola vez y valida que el archivo sea una imagen real.
    image = _load_rgb_image(image_bytes)

    brightness, variance = _image_statistics(image)
    if not _is_valid_sky_image(brightness, variance):
        logger.info(
            "Imagen descartada por baja calidad (brillo=%.1f, varianza=%.1f)",
            brightness,
            variance,
        )
        return _invalid_result()

    features = _scene_features(image)
    if _looks_like_interior(features):
        logger.info(
            "Imagen descartada por falta de cielo abierto: azul=%.2f, frio=%.2f, "
            "calido=%.2f, neutro=%.2f, grad_std=%.2f, bordes=%.3f",
            features["blue_sky_fraction"],
            features["cool_bias_fraction"],
            features["warm_fraction"],
            features["neutral_fraction"],
            features["gradient_std"],
            features["edge_density"],
        )
        return _interior_result()

    tensor = np.asarray(
        image.resize(IMAGE_SIZE, Image.Resampling.BILINEAR), dtype=np.float32
    ) / 255.0
    tensor = (tensor - IMAGENET_MEAN) / IMAGENET_STD

    result = _infer_with_model(tensor)
    if result is not None:
        return result

    return _heuristic_analysis(image)
