"""Tests del filtro de calidad y el clasificador heurístico de visión."""

from app.services import vision_model
from tests.image_helpers import dark_image, flat_white_image, sky_image


def test_dark_photo_is_rejected_without_rain():
    result = vision_model.analyze_sky_image(dark_image())

    assert result["is_valid"] is False
    assert result["status"] == vision_model.INVALID_IMAGE_STATUS
    assert result["rain_probability"] == 0.0


def test_flat_white_surface_is_rejected_without_rain():
    result = vision_model.analyze_sky_image(flat_white_image())

    assert result["is_valid"] is False
    assert result["status"] == vision_model.INVALID_IMAGE_STATUS
    assert result["rain_probability"] == 0.0


def test_generated_sky_with_texture_and_gradient_is_valid():
    result = vision_model.analyze_sky_image(sky_image())

    assert result["is_valid"] is True
    assert result["status"] == "ok"
    assert 0.0 <= result["rain_probability"] <= 100.0
