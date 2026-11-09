"""Imágenes sintéticas para los tests de visión (sin archivos externos)."""

from __future__ import annotations

from io import BytesIO

import numpy as np
from PIL import Image


def _to_png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def dark_image() -> bytes:
    """Foto negra: simula lente tapado."""
    return _to_png(Image.new("RGB", (224, 224), (0, 0, 0)))


def flat_white_image() -> bytes:
    """Superficie blanca sin textura: pared o techo plano."""
    return _to_png(Image.new("RGB", (224, 224), (248, 248, 248)))


def sky_image() -> bytes:
    """Cielo azul sintético con gradiente vertical y textura de nubes."""
    size = 224
    vertical = np.linspace(0.0, 1.0, size)[:, None]
    horizontal = np.linspace(0.0, 1.0, size)[None, :]

    top = np.array([35.0, 110.0, 205.0], dtype=np.float32)
    bottom = np.array([150.0, 205.0, 245.0], dtype=np.float32)
    gradient = top + (bottom - top) * vertical
    image = np.broadcast_to(gradient, (size, size, 3)).copy()

    clouds = (np.sin(horizontal * 12 + vertical * 5) + np.cos(vertical * 18)) * 18
    noise = np.random.default_rng(7).normal(0, 6, (size, size))
    image += clouds[..., None] * 0.4 + noise[..., None]

    return _to_png(
        Image.fromarray(np.clip(image, 0, 255).astype(np.uint8), mode="RGB")
    )
