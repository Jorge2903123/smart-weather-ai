import { useCallback, useEffect, useMemo, useState } from "react";
import Header from "./components/Header";
import CurrentWeather from "./components/CurrentWeather";
import ForecastSection from "./components/ForecastSection";
import SkyVisionCard from "./components/SkyVisionCard";
import AssistantPanel from "./components/AssistantPanel";
import RecommendationBadge from "./components/RecommendationBadge";
import { useGeolocation } from "./hooks/useGeolocation";
import { askAssistant, getCurrentWeather, getForecast } from "./services/api";

export default function App() {
  const [weather, setWeather] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [assistant, setAssistant] = useState(null);

  const [loadingWeather, setLoadingWeather] = useState(true);
  const [loadingAssistant, setLoadingAssistant] = useState(false);
  const [error, setError] = useState("");
  const [online, setOnline] = useState(true);

  const {
    status: locationStatus,
    error: locationError,
    requestLocation,
  } = useGeolocation();

  const loadWeather = useCallback(async (position = null) => {
    setLoadingWeather(true);
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
      setOnline(true);
    } catch (err) {
      setError(err.message);
      setOnline(false);
    } finally {
      setLoadingWeather(false);
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
        setOnline(true);
      } catch (err) {
        setError(err.message);
        setOnline(false);
      } finally {
        setLoadingAssistant(false);
      }
    },
    [weather, analysis, forecast]
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

  const usingApproximateLocation =
    weather?.location_source === "ip" ||
    weather?.location_source === "default" ||
    locationStatus === "denied" ||
    locationStatus === "unavailable";

  const locationHint = usingApproximateLocation
    ? "Usando ubicación aproximada por IP"
    : "";

  const locationNotice =
    locationStatus === "denied"
      ? `${locationError || "Permiso de ubicación denegado."} Activa la ubicación para Safari en Ajustes y toca GPS para reintentar.`
      : "";

  return (
    <div className="min-h-dvh px-4 pt-[max(1rem,env(safe-area-inset-top))]">
      <div className="safe-bottom mx-auto w-full max-w-md lg:max-w-5xl">
        <Header
          location={
            weather?.location ||
            (locationStatus === "requesting"
              ? "Detectando ubicación…"
              : "Mi ubicación")
          }
          hint={locationHint}
          updatedAt={weather?.updated_at}
          online={online}
          showGpsButton={usingApproximateLocation}
          gpsLoading={locationStatus === "requesting"}
          onRequestGps={refreshLocation}
        />

        {locationNotice && (
          <div
            role="alert"
            className="mt-2 flex items-start justify-between gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800"
          >
            <p className="leading-relaxed">{locationNotice}</p>
            <button
              type="button"
              onClick={refreshLocation}
              className="shrink-0 font-semibold underline"
            >
              Reintentar GPS
            </button>
          </div>
        )}

        {error && (
          <div className="mt-2 rounded-2xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">
            <div className="flex items-start justify-between gap-3">
              <p className="leading-relaxed">{error}</p>
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

        <main className="mt-3 grid gap-3 lg:grid-cols-2 lg:items-start">
          <div className="space-y-3">
            <CurrentWeather weather={weather} loading={loadingWeather} />
            <RecommendationBadge recommendations={recommendations} />
            <ForecastSection
              forecast={forecast}
              weather={weather}
              loading={loadingWeather}
            />
          </div>

          <div className="space-y-3">
            <AssistantPanel
              answer={assistant?.answer}
              source={assistant?.source}
              loading={loadingAssistant}
              onAsk={handleAsk}
            />
            <SkyVisionCard analysis={analysis} onAnalyzed={setAnalysis} />
          </div>
        </main>

        <footer className="mt-4 pb-2 text-center text-[11px] text-slate-400">
          Smart Weather AI · MVP académico · Visión, pronóstico y voz
        </footer>
      </div>
    </div>
  );
}
