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

# Etiquetas de salida de la CNN (orden estable para mapear índices del modelo).
CLASS_LABELS = [
    ("Cielo despejado", "Soleado"),
    ("Parcialmente nublado", "Nublado"),
    ("Nubes densas", "Posible lluvia"),
    ("Tormenta", "Alerta de lluvia"),
    ("Niebla", "Visibilidad reducida"),
]


def preprocess_image(image_bytes: bytes) -> np.ndarray:
    """Convierte bytes en un tensor RGB 224x224x3 normalizado (NHWC)."""
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("El archivo recibido no es una imagen válida.") from exc

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
        return {
            "label": label,
            "confidence": round(float(probs[index].item()), 2),
            "state": state,
            "source": "cnn",
        }
    except Exception as exc:  # pragma: no cover - depende del entorno
        logger.warning("Fallo la inferencia CNN, usando respaldo: %s", exc)
        return None


def _heuristic_analysis(image_bytes: bytes) -> dict:
    """
    Clasificador de respaldo basado en brillo, dominancia de azul y contraste.

    No pretende sustituir a la CNN: entrega resultados plausibles y estables
    para que la demo funcione sin pesos entrenados.
    """
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    image = image.resize((64, 64), Image.Resampling.BILINEAR)
    pixels = np.asarray(image, dtype=np.float32)

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

    return {
        "label": label,
        "confidence": confidence,
        "state": state,
        "source": "heuristic",
    }


def analyze_sky_image(image_bytes: bytes) -> dict:
    """Punto de entrada del servicio de visión."""
    if not image_bytes:
        raise ValueError("La imagen está vacía.")

    # El preprocesamiento valida que el archivo sea una imagen real.
    image_array = preprocess_image(image_bytes)

    result = _infer_with_model(image_array)
    if result is not None:
        return result

    return _heuristic_analysis(image_bytes)
