import axios from "axios";

/**
 * Cliente HTTP del backend.
 *
 * En desarrollo local usa http://localhost:8000.
 * Para probar desde un iPhone en la misma red, crea un `.env` con:
 *   VITE_API_URL=http://192.168.1.50:8000
 * (usa la IP LAN de tu computadora, no localhost).
 */
const rawBase = import.meta.env.VITE_API_URL || "";
const API_BASE = "/api";

const client = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
});

function toFriendlyError(error) {
  if (error.code === "ECONNABORTED") {
    return new Error("El servidor tardó demasiado en responder.");
  }
  if (!error.response) {
    return new Error(
      "No se pudo conectar con el backend. Verifica la IP y que FastAPI esté corriendo."
    );
  }
  const detail = error.response.data?.detail;
  return new Error(
    typeof detail === "string" ? detail : "Ocurrió un error al procesar la solicitud."
  );
}

function locationParams({ lat, lon } = {}) {
  if (Number.isFinite(lat) && Number.isFinite(lon)) {
    return { lat, lon };
  }
  // Sin coordenadas el backend resuelve la ubicación aproximada por IP.
  return {};
}

export async function getCurrentWeather(coords = {}) {
  try {
    const { data } = await client.get("/weather/current", {
      params: locationParams(coords),
    });
    return data;
  } catch (error) {
    throw toFriendlyError(error);
  }
}

export async function getForecast({ lat, lon, hours = 6 } = {}) {
  try {
    const { data } = await client.get("/weather/forecast", {
      params: { ...locationParams({ lat, lon }), hours },
    });
    return data;
  } catch (error) {
    throw toFriendlyError(error);
  }
}

export async function analyzeSky(file) {
  const formData = new FormData();
  formData.append("image", file);

  try {
    const { data } = await client.post("/vision/analyze", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  } catch (error) {
    throw toFriendlyError(error);
  }
}

export async function askAssistant(prompt, currentContext = {}) {
  try {
    const { data } = await client.post("/assistant/ask", {
      prompt,
      current_context: currentContext,
    });
    return data;
  } catch (error) {
    throw toFriendlyError(error);
  }
}

export { API_BASE };
