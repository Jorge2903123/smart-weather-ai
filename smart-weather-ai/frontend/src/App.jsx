import { useCallback, useEffect, useMemo, useState } from "react";
import AdminModal from "./components/AdminModal";
import MainWeatherView from "./components/MainWeatherView";
import { useGeolocation } from "./hooks/useGeolocation";
import {
  analyzeSky,
  askAssistant,
  getCurrentWeather,
  getForecast,
} from "./services/api";

function conditionKey(weather) {
  const text = `${weather?.condition ?? ""} ${weather?.sky_state ?? ""}`.toLowerCase();
  if (text.includes("tormenta") || text.includes("trueno")) return "storm";
  if (
    text.includes("lluvia") ||
    text.includes("llovizna") ||
    text.includes("chubasco")
  ) {
    return "rain";
  }
  if (text.includes("parcial") || text.includes("mayormente despejado")) {
    return "partly_cloudy";
  }
  if (
    text.includes("nublado") ||
    text.includes("niebla") ||
    text.includes("variable") ||
    text.includes("nieve")
  ) {
    return "cloudy";
  }
  if (text.includes("despejado") || text.includes("soleado")) return "clear_day";
  return "partly_cloudy";
}

function forecastIcon(rainProbability, currentCondition) {
  if (currentCondition === "storm") return "cloud-lightning";
  if (currentCondition === "rain" || rainProbability >= 50) return "cloud-rain";
  if (currentCondition === "clear_day") return "sun";
  if (currentCondition === "cloudy") return "cloud";
  return "cloud-sun";
}

export default function App() {
  const [weather, setWeather] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [assistant, setAssistant] = useState(null);
  const [adminOpen, setAdminOpen] = useState(false);
  const [loadingAssistant, setLoadingAssistant] = useState(false);
  const [error, setError] = useState("");

  const {
    status: locationStatus,
    error: locationError,
    requestLocation,
  } = useGeolocation();

  const loadWeather = useCallback(async (position = null) => {
    setError("");

    try {
      // Con GPS se envían lat/lon; si no, el backend usa la IP pública.
      const params = position
        ? { lat: position.latitude, lon: position.longitude }
        : {};

      const [current, projection] = await Promise.all([
        getCurrentWeather(params),
        getForecast(params),
      ]);
      setWeather(current);
      setForecast(projection);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  const refreshLocation = useCallback(async () => {
    const position = await requestLocation();
    await loadWeather(position);
  }, [requestLocation, loadWeather]);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const position = await requestLocation();
      if (!cancelled) await loadWeather(position);
    })();

    return () => {
      cancelled = true;
    };
  }, [requestLocation, loadWeather]);

  const handleAsk = useCallback(
    async (prompt) => {
      setLoadingAssistant(true);
      setError("");

      try {
        const response = await askAssistant(prompt, {
          current: weather,
          vision: analysis,
          forecast,
        });
        setAssistant(response);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoadingAssistant(false);
      }
    },
    [weather, analysis, forecast]
  );

  const handlePhoto = useCallback(
    async (file) => {
      setError("");

      try {
        const result = await analyzeSky(file, weather?.location ?? "");
        setAnalysis(result);
      } catch (err) {
        setError(err.message);
      }
    },
    [weather?.location]
  );

  // Recomendación inmediata (sin esperar al asistente) derivada del pronóstico.
  const recommendations = useMemo(() => {
    if (assistant?.recommendations) return assistant.recommendations;
    if (!weather) return null;

    const points = forecast?.points ?? [];
    const maxRain = points.length
      ? Math.max(...points.map((point) => point.rain_probability))
      : 0;
    const visionState = `${analysis?.state ?? ""}`.toLowerCase();

    const needUmbrella =
      maxRain >= 40 || weather.humidity >= 80 || visionState.includes("lluvia");
    const needJacket = weather.temperature <= 18 || weather.wind_kph >= 25;
    const needSunscreen =
      weather.temperature >= 26 && maxRain < 30 && !needUmbrella;

    let summary = "Día agradable, disfrútalo";
    if (needUmbrella) summary = "Lleva paraguas por si acaso";
    else if (needJacket) summary = "Usa una chamarra ligera";
    else if (needSunscreen) summary = "Aplica protector solar";

    return {
      need_umbrella: needUmbrella,
      need_jacket: needJacket,
      need_sunscreen: needSunscreen,
      summary,
    };
  }, [assistant, weather, forecast, analysis]);

  const viewData = useMemo(() => {
    const condition = conditionKey(weather);
    const points = forecast?.points ?? [];
    const isLoading = !weather;
    const forecastSimulated = forecast?.source === "simulated";
    const currentLive = weather?.data_source === "open-meteo";
    const isLive = currentLive && !forecastSimulated;
    const advice = isLoading
      ? null
      : loadingAssistant
        ? "Consultando el clima para tu pregunta…"
        : assistant?.answer ||
          recommendations?.summary ||
          "Revisa el pronóstico antes de salir.";

    return {
      is_loading: isLoading,
      data_sources: {
        weather: weather?.data_source ?? null,
        forecast: forecast?.source ?? null,
        is_live: isLive,
      },
      current_weather: weather
        ? {
            temperature: weather.temperature,
            condition,
            humidity: weather.humidity,
            wind_speed_kmh: Math.round(weather.wind_kph ?? 0),
            uv_index: Math.round(weather.uv_index ?? 0),
          }
        : null,
      hourly_forecast: points.map((point) => {
        const rainProbability = point.rain_probability ?? 0;
        return {
          time: point.time,
          temp: Math.round(point.temperature),
          rain_prob: rainProbability,
          icon: forecastIcon(rainProbability, condition),
        };
      }),
      vision_diagnosis: {
        has_image: analysis?.has_image ?? Boolean(analysis),
        is_valid: analysis?.is_valid ?? analysis?.status === "ok",
        sky_label: analysis?.sky_label ?? analysis?.label ?? null,
        message: analysis?.message ?? analysis?.description ?? null,
        rain_probability: analysis?.rain_probability ?? null,
        confidence: analysis?.confidence ?? null,
      },
      ai_recommendation: {
        actionable_advice: advice,
        summary: assistant ? assistant?.recommendations?.summary ?? null : null,
        speech_text: advice,
      },
      location: {
        current:
          weather?.location ||
          (locationStatus === "requesting"
            ? "Detectando ubicación…"
            : "Mi ubicación"),
        destination:
          assistant?.destination?.location?.display_name ||
          assistant?.destination?.query ||
          null,
      },
    };
  }, [
    weather,
    forecast,
    analysis,
    assistant,
    recommendations,
    loadingAssistant,
    locationStatus,
  ]);

  const locationNotice =
    locationStatus === "denied"
      ? `${locationError || "Permiso de ubicación denegado."} Activa la ubicación para Safari en Ajustes y toca Reintentar.`
      : "";

  return (
    <div className="relative">
      <MainWeatherView
        data={viewData}
        onPhoto={handlePhoto}
        onAsk={handleAsk}
        onOpenAdmin={() => setAdminOpen(true)}
      />

      {(error || locationNotice) && (
        <div
          role="alert"
          className={`fixed inset-x-3 top-[max(0.75rem,env(safe-area-inset-top))] z-40 mx-auto max-w-md rounded-2xl p-3 text-xs shadow-lg backdrop-blur ${
            error
              ? "bg-rose-600/95 text-white"
              : "bg-amber-100/95 text-amber-900"
          }`}
        >
          <div className="flex items-start justify-between gap-3">
            <p className="leading-relaxed">{error || locationNotice}</p>
            <button
              type="button"
              onClick={refreshLocation}
              className="shrink-0 font-semibold underline"
            >
              Reintentar
            </button>
          </div>
        </div>
      )}

      <AdminModal open={adminOpen} onClose={() => setAdminOpen(false)} />
    </div>
  );
}
