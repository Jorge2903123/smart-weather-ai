import { useCallback, useRef, useState } from "react";

const ERROR_MESSAGES = {
  1: "Permiso de ubicación denegado.",
  2: "No se pudo obtener tu ubicación.",
  3: "La ubicación tardó demasiado en responder.",
};

/**
 * Geolocalización nativa del dispositivo.
 *
 * `requestLocation()` devuelve una promesa con `{latitude, longitude}` o `null`
 * si el permiso fue denegado / el GPS falló. En ese caso el backend aplica el
 * fallback por IP pública, por lo que la app sigue funcionando.
 */
export function useGeolocation({ timeout = 15000 } = {}) {
  const [coords, setCoords] = useState(null);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const pendingRef = useRef(null);

  const requestLocation = useCallback(() => {
    // Evita prompts duplicados si el componente se re-renderiza rápido.
    if (pendingRef.current) return pendingRef.current;

    if (!("geolocation" in navigator)) {
      setStatus("unavailable");
      setError("Este dispositivo no soporta geolocalización.");
      return Promise.resolve(null);
    }

    setStatus("requesting");
    setError("");

    const promise = new Promise((resolve) => {
      navigator.geolocation.getCurrentPosition(
        (position) => {
          const nextCoords = {
            latitude: Number(position.coords.latitude.toFixed(6)),
            longitude: Number(position.coords.longitude.toFixed(6)),
          };
          setCoords(nextCoords);
          setStatus("granted");
          pendingRef.current = null;
          resolve(nextCoords);
        },
        (geoError) => {
          console.error("Error GPS iOS:", geoError.code, geoError.message);
          setStatus(geoError.code === 1 ? "denied" : "unavailable");
          setError(ERROR_MESSAGES[geoError.code] || "Ubicación no disponible.");
          pendingRef.current = null;
          resolve(null);
        },
        {
          enableHighAccuracy: true,
          timeout,
          maximumAge: 60000,
        }
      );
    });

    pendingRef.current = promise;
    return promise;
  }, [timeout]);

  return { coords, status, error, requestLocation };
}
