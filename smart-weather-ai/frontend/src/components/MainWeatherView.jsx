import { useMemo, useRef, useState } from "react";
import { useSpeech } from "../hooks/useSpeech";
import {
  ArrowRight,
  Camera,
  Cloud,
  CloudLightning,
  CloudRain,
  CloudSun,
  Droplets,
  Image as ImageIcon,
  Lock,
  MapPin,
  Mic,
  Pause,
  Send,
  Sun,
  Umbrella,
  Volume2,
  Wind,
} from "lucide-react";

const CONDITION = {
  clear_day: {
    label: "Despejado",
    gradient: "from-amber-300 via-orange-400 to-sky-400",
    text: "text-slate-900",
    subtext: "text-slate-700",
    Icon: Sun,
    iconClass: "text-amber-500 animate-[spin_24s_linear_infinite]",
  },
  partly_cloudy: {
    label: "Parcialmente nublado",
    gradient: "from-sky-300 via-sky-400 to-slate-300",
    text: "text-slate-900",
    subtext: "text-slate-700",
    Icon: CloudSun,
    iconClass: "text-amber-400",
  },
  cloudy: {
    label: "Nublado",
    gradient: "from-slate-300 via-slate-400 to-slate-500",
    text: "text-slate-900",
    subtext: "text-slate-700",
    Icon: Cloud,
    iconClass: "text-slate-500",
  },
  rain: {
    label: "Lluvia",
    gradient: "from-slate-800 via-teal-900 to-slate-900",
    text: "text-white",
    subtext: "text-teal-100/80",
    Icon: CloudRain,
    iconClass: "text-sky-300",
  },
  storm: {
    label: "Tormenta",
    gradient: "from-slate-900 via-indigo-950 to-teal-950",
    text: "text-white",
    subtext: "text-indigo-100/80",
    Icon: CloudLightning,
    iconClass: "text-yellow-300",
  },
};

const FORECAST_ICONS = {
  sun: Sun,
  "cloud-sun": CloudSun,
  cloud: Cloud,
  "cloud-rain": CloudRain,
  "cloud-lightning": CloudLightning,
};

function uvLabel(uv = 0) {
  if (uv <= 2) return "Bajo";
  if (uv <= 5) return "Moderado";
  if (uv <= 7) return "Alto";
  if (uv <= 10) return "Muy alto";
  return "Extremo";
}

export default function MainWeatherView({
  data,
  photoUrl = null,
  onPhoto,
  onAsk,
  onOpenAdmin,
}) {
  const [query, setQuery] = useState("");
  const [localPhoto, setLocalPhoto] = useState(null);
  const cameraRef = useRef(null);
  const galleryRef = useRef(null);
  const {
    supported: speechSupported,
    listening,
    speaking,
    error: speechError,
    start: startListening,
    stop: stopListening,
    speak,
    cancelSpeech,
    unlockAudio,
  } = useSpeech({
    onResult: (text) => {
      setQuery(text);
      onAsk?.(text);
    },
  });

  const current = data?.current_weather ?? null;
  const forecast = data?.hourly_forecast ?? [];
  const vision = data?.vision_diagnosis ?? {};
  const ai = data?.ai_recommendation ?? {};
  const location = data?.location ?? {};
  const isLive = Boolean(data?.data_sources?.is_live);

  const condition = CONDITION[current?.condition] ?? CONDITION.partly_cloudy;
  const ConditionIcon = condition.Icon;
  const preview = photoUrl || localPhoto;
  const numericVisionRain = Number(vision.rain_probability);
  const visionRain =
    vision.rain_probability != null && Number.isFinite(numericVisionRain)
      ? Math.round(numericVisionRain)
      : null;

  const peak = useMemo(() => {
    if (!forecast.length) return null;
    return forecast.reduce((a, b) => (b.rain_prob > a.rain_prob ? b : a));
  }, [forecast]);

  const handlePhotoFile = (file) => {
    if (!file) return;
    setLocalPhoto(URL.createObjectURL(file));
    onPhoto?.(file);
  };

  const toggleSpeech = () => {
    if (speaking) {
      cancelSpeech();
      return;
    }
    const text = ai.speech_text || ai.actionable_advice || ai.summary;
    if (!text) return;
    unlockAudio();
    speak(text);
  };

  const toggleMic = () => {
    if (!speechSupported) {
      alert("Reconocimiento de voz no soportado directamente en este navegador. Usa el teclado.");
      return;
    }
    unlockAudio();
    if (listening) {
      stopListening();
      return;
    }
    startListening();
  };

  const submitAsk = (e) => {
    e?.preventDefault();
    const text = query.trim();
    if (!text) return;
    onAsk?.(text);
    setQuery("");
  };

  return (
    <div
      className={`mx-auto flex h-[100dvh] w-full max-w-md flex-col overflow-hidden bg-gradient-to-b ${condition.gradient} pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)]`}
    >
      <main className="flex-1 overflow-y-auto px-4 pb-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {/* Cabecera / Ubicación & Acceso a Admin */}
        <header className="flex items-start justify-between pt-3">
          <div className={`flex items-start gap-1.5 ${condition.text}`}>
            <MapPin className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <p className="text-[15px] font-semibold leading-tight">
                {location.current || "Detectando ubicación..."}
              </p>
              {location.destination && (
                <p className="flex items-center gap-1 text-xs opacity-80">
                  <ArrowRight className="h-3 w-3" />
                  Destino: {location.destination}
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <span
              className={`flex shrink-0 items-center gap-1.5 rounded-full bg-white/85 px-2.5 py-1 text-[11px] font-semibold shadow-sm backdrop-blur ${
                isLive ? "text-emerald-700" : "text-slate-600"
              }`}
              title={
                isLive
                  ? "Datos actuales de Open-Meteo"
                  : "Pronóstico simulado o datos no disponibles"
              }
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  isLive ? "animate-pulse bg-emerald-500" : "bg-slate-400"
                }`}
              />
              {isLive ? "En vivo" : "Simulado"}
            </span>
            {onOpenAdmin && (
              <button
                type="button"
                onClick={onOpenAdmin}
                aria-label="Panel Admin"
                className="rounded-full bg-white/80 p-1.5 text-slate-700 shadow-sm transition active:scale-90"
              >
                <Lock className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </header>

        {/* Hero del Clima */}
        {current ? (
          <section className="mt-3 rounded-[28px] bg-white/90 p-5 shadow-xl shadow-black/5 backdrop-blur">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-[11px] font-bold tracking-[0.18em] text-slate-400">AHORA</p>
              <p className="mt-1 flex items-start text-slate-900">
                <span className="text-[64px] font-extrabold leading-none tracking-tight">
                  {Math.round(current.temperature ?? 0)}
                </span>
                <span className="mt-2 text-2xl font-semibold text-slate-400">°C</span>
              </p>
              <p className="mt-2 text-[17px] font-semibold text-slate-800">{condition.label}</p>
              {peak && peak.rain_prob >= 50 && (
                <p className="mt-1 inline-flex items-center gap-1 rounded-full bg-sky-100 px-2 py-0.5 text-xs font-semibold text-sky-700">
                  <Umbrella className="h-3.5 w-3.5" />
                  {peak.rain_prob}% de lluvia a las {peak.time}
                </p>
              )}
            </div>
            <ConditionIcon
              className={`h-20 w-20 shrink-0 ${condition.iconClass}`}
              strokeWidth={1.5}
            />
          </div>

          {/* Métricas: Humedad, Viento, UV */}
          <div className="mt-5 grid grid-cols-3 gap-2">
            <div className="rounded-2xl bg-slate-100/80 px-3 py-2.5 text-center">
              <Droplets className="mx-auto h-4 w-4 text-sky-600" />
              <p className="mt-1 text-sm font-bold text-slate-800">{current.humidity}%</p>
              <p className="text-[11px] text-slate-500">Humedad</p>
            </div>
            <div className="rounded-2xl bg-slate-100/80 px-3 py-2.5 text-center">
              <Wind className="mx-auto h-4 w-4 text-teal-600" />
              <p className="mt-1 text-sm font-bold text-slate-800">{current.wind_speed_kmh} km/h</p>
              <p className="text-[11px] text-slate-500">Viento</p>
            </div>
            <div className="rounded-2xl bg-slate-100/80 px-3 py-2.5 text-center">
              <Sun className="mx-auto h-4 w-4 text-amber-500" />
              <p className="mt-1 text-sm font-bold text-slate-800">
                UV {current.uv_index} · {uvLabel(current.uv_index)}
              </p>
              <p className="text-[11px] text-slate-500">Radiación</p>
            </div>
          </div>
          </section>
        ) : (
          <section className="mt-3 rounded-[28px] bg-white/90 p-5 shadow-xl shadow-black/5 backdrop-blur">
            <p className="text-[11px] font-bold tracking-[0.18em] text-slate-400">AHORA</p>
            <p className="mt-2 text-sm font-semibold text-slate-500">Cargando clima…</p>
            <div className="mt-3 h-14 w-28 animate-pulse rounded-2xl bg-slate-200" />
            <div className="mt-5 grid grid-cols-3 gap-2">
              {[0, 1, 2].map((item) => (
                <div
                  key={item}
                  className="h-20 animate-pulse rounded-2xl bg-slate-100"
                />
              ))}
            </div>
          </section>
        )}

        {/* Consejo Accionable */}
        {current && ai.actionable_advice && (
          <section className="mt-3 rounded-[28px] bg-slate-900 p-5 text-white shadow-xl shadow-black/10">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[11px] font-bold tracking-[0.18em] text-amber-300">QUÉ HACER</p>
                <p className="mt-2 text-[15px] font-medium leading-snug">{ai.actionable_advice}</p>
                {ai.summary && (
                  <p className="mt-2 text-[13px] leading-snug text-white/70">{ai.summary}</p>
                )}
              </div>
              <button
                type="button"
                onClick={toggleSpeech}
                aria-label={speaking ? "Pausar voz" : "Escuchar consejo"}
                className="shrink-0 rounded-full bg-white/15 p-3 text-white transition active:scale-95"
              >
                {speaking ? <Pause className="h-5 w-5" /> : <Volume2 className="h-5 w-5" />}
              </button>
            </div>
          </section>
        )}

        {/* Próximas 6 horas */}
        {forecast.length > 0 && (
          <section className="mt-3 rounded-[28px] bg-white/90 p-5 shadow-xl shadow-black/5 backdrop-blur">
            <div className="flex items-baseline justify-between">
              <h2 className="text-[11px] font-bold tracking-[0.18em] text-slate-400">PRÓXIMAS 6 HORAS</h2>
              <span className="text-xs font-medium text-slate-500">Desliza →</span>
            </div>
            <div className="mt-3 flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              {forecast.map((h) => {
                const Icon = FORECAST_ICONS[h.icon] ?? CloudSun;
                const rainy = h.rain_prob >= 50;
                return (
                  <div
                    key={h.time}
                    className={`flex w-[76px] shrink-0 snap-start flex-col items-center rounded-2xl px-2 py-3 ${
                      rainy ? "bg-sky-100 text-sky-900" : "bg-slate-100 text-slate-800"
                    }`}
                  >
                    <span className="text-xs font-semibold">{h.time}</span>
                    <Icon className="my-2 h-6 w-6" strokeWidth={1.75} />
                    <span className="text-sm font-bold">{h.temp}°</span>
                    <span className={`mt-0.5 text-[11px] font-semibold ${rainy ? "text-sky-700" : "text-slate-500"}`}>
                      {h.rain_prob}% lluvia
                    </span>
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {/* Visión del cielo */}
        <section className="mt-3 rounded-[28px] bg-white/90 p-5 shadow-xl shadow-black/5 backdrop-blur">
          <h2 className="text-[11px] font-bold tracking-[0.18em] text-slate-400">VISIÓN DEL CIELO</h2>
          <p className="mt-1 text-[15px] font-semibold text-slate-800">¿Va a llover? Súbele una foto al cielo</p>

          {preview && vision.has_image ? (
            <div className="relative mt-3 overflow-hidden rounded-2xl">
              <img src={preview} alt="Foto del cielo analizada" className="h-40 w-full object-cover" />
              {vision.is_valid === false ? (
                <div className="absolute inset-x-0 bottom-0 bg-amber-500/95 p-3 text-amber-950">
                  <p className="text-sm font-bold leading-snug">
                    No es cielo abierto · Reintenta apuntando al cielo
                  </p>
                  {vision.message && (
                    <p className="mt-1 text-[11px] font-medium leading-snug text-amber-900/90">
                      {vision.message}
                    </p>
                  )}
                </div>
              ) : (
                <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/75 to-transparent p-3 pt-8">
                  <p className="text-sm font-semibold text-white">{vision.sky_label || "Cielo analizado"}</p>
                  <p className="text-xs text-white/85">
                    {visionRain != null
                      ? `${visionRain}% de lluvia estimada por la foto`
                      : peak
                        ? `Pico del pronóstico: ${peak.rain_prob}% a las ${peak.time}`
                        : "Análisis completado"}
                    {visionRain != null && peak
                      ? ` · pico ${peak.rain_prob}% a las ${peak.time}`
                      : ""}
                  </p>
                </div>
              )}
              <span className="absolute left-3 top-3 rounded-full bg-white/90 px-2.5 py-1 text-[11px] font-bold text-slate-800">
                {vision.is_valid === false
                  ? "Foto no válida"
                  : isLive
                    ? "Foto + pronóstico real"
                    : "Foto + pronóstico"}
              </span>
            </div>
          ) : (
            <p className="mt-1 text-[13px] leading-snug text-slate-500">
              La IA cruza tu foto con el pronóstico de tu ubicación para estimar la lluvia real.
            </p>
          )}

          <div className="mt-3 grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => cameraRef.current?.click()}
              className="flex items-center justify-center gap-2 rounded-2xl bg-slate-900 px-3 py-3 text-sm font-semibold text-white transition active:scale-[0.98]"
            >
              <Camera className="h-4 w-4" />
              Tomar foto
            </button>
            <button
              type="button"
              onClick={() => galleryRef.current?.click()}
              className="flex items-center justify-center gap-2 rounded-2xl bg-slate-100 px-3 py-3 text-sm font-semibold text-slate-800 transition active:scale-[0.98]"
            >
              <ImageIcon className="h-4 w-4" />
              Elegir de galería
            </button>
          </div>

          <input
            ref={cameraRef}
            type="file"
            accept="image/*"
            capture="environment"
            className="hidden"
            onChange={(e) => handlePhotoFile(e.target.files?.[0])}
          />
          <input
            ref={galleryRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => handlePhotoFile(e.target.files?.[0])}
          />
        </section>

        <p className="mt-4 text-center text-[11px] text-white/80">Smart Weather AI · Visión, pronóstico y voz</p>
      </main>

      {/* Dock inferior flotante */}
      <footer className="px-4 pb-2">
        <form onSubmit={submitAsk} className="flex items-center gap-2 rounded-full bg-white p-1.5 shadow-2xl shadow-black/20">
          <button
            type="button"
            onClick={toggleMic}
            aria-label={listening ? "Dejar de escuchar" : "Hablar con la IA"}
            className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full transition active:scale-95 ${
              listening ? "animate-pulse bg-red-500 text-white" : "bg-slate-900 text-white"
            }`}
          >
            <Mic className="h-5 w-5" />
          </button>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Voy a Santa Fe..."
            aria-label="Pregunta a dónde vas"
            className="min-w-0 flex-1 bg-transparent px-1 text-[15px] text-slate-800 outline-none placeholder:text-slate-400"
          />
          <button
            type="submit"
            aria-label="Enviar pregunta"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-sky-600 text-white transition active:scale-95"
          >
            <Send className="h-5 w-5" />
          </button>
        </form>
        {speechError ? (
          <p
            role="alert"
            className="mx-auto mt-1.5 w-fit rounded-full bg-rose-600/90 px-2 py-1 text-center text-[11px] font-medium text-white"
          >
            {speechError}
          </p>
        ) : (
          <p className="mt-1.5 text-center text-[11px] text-white/70">
            {listening ? "Escuchando… di a dónde vas" : "Pregunta por voz o texto: “¿Necesito paraguas hoy?”"}
          </p>
        )}
      </footer>
    </div>
  );
}
