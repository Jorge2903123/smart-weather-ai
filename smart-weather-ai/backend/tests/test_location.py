"""Geocodificación con sesgo de proximidad, sin llamadas de red."""

from app.services import location_service


def _no_network(*args, **kwargs):
    raise AssertionError("El test no debe llamar a la red real")


def _huixquilucan() -> dict:
    return location_service._build_location(
        city="Huixquilucan",
        state="México",
        country="México",
        country_code="mx",
        latitude=19.3603,
        longitude=-99.3516,
        source="geocoded",
    )


def test_nominatim_resolves_destination_with_user_proximity(monkeypatch):
    calls = []

    def fake_nominatim(query, latitude, longitude, country_code):
        calls.append((query, latitude, longitude, country_code))
        if query == "huixqui, México":
            return _huixquilucan()
        return None

    monkeypatch.setattr(location_service, "_geocode_place_cached", fake_nominatim)
    monkeypatch.setattr(location_service.requests, "get", _no_network)

    result = location_service.dynamic_geocode("huixqui", 19.4, -99.2)

    assert result is not None
    assert result["display_name"] == "Huixquilucan, Méx."
    assert calls[0] == ("huixqui, México", 19.4, -99.2, "mx")


def test_photon_fallback_keeps_proximity_bias(monkeypatch):
    nominatim_calls = []
    photon_calls = []

    def fake_nominatim(query, latitude, longitude, country_code):
        nominatim_calls.append((query, latitude, longitude, country_code))
        return None

    def fake_photon(query, latitude, longitude):
        photon_calls.append((query, latitude, longitude))
        if query == "Santa Fe, México":
            return location_service._build_location(
                city="Santa Fe",
                state="Ciudad de México",
                country="México",
                country_code="mx",
                latitude=19.365,
                longitude=-99.26,
                source="geocoded",
            )
        return None

    monkeypatch.setattr(location_service, "_geocode_place_cached", fake_nominatim)
    monkeypatch.setattr(location_service, "_photon_geocode_cached", fake_photon)
    monkeypatch.setattr(location_service.requests, "get", _no_network)

    result = location_service.dynamic_geocode("Santa Fe", 19.4, -99.2)

    assert result is not None
    assert result["display_name"] == "Santa Fe, CDMX"
    assert photon_calls[0] == ("Santa Fe, México", 19.4, -99.2)
