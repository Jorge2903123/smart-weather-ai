function faceFor(weather) {
  if (!weather) return { face: "🙂", label: "Cargando" };
  const state = `${weather.sky_state} ${weather.condition}`.toLowerCase();
  if (state.includes("lluvia") || state.includes("tormenta")) {
    return { face: "😟", label: "Posible lluvia" };
  }
  if (state.includes("nublado") || state.includes("niebla")) {
    return { face: "🤔", label: "Cielo nublado" };
  }
  return { face: "😊", label: "Buen clima" };
}

export default function CurrentWeather({ weather, loading }) {
  if (loading && !weather) {
    return (
      <section className="card p-6">
        <div className="h-4 w-24 animate-pulse rounded bg-slate-100" />
        <div className="mt-6 h-16 w-40 animate-pulse rounded bg-slate-100" />
        <div className="mt-4 h-4 w-32 animate-pulse rounded bg-slate-100" />
      </section>
    );
  }

  if (!weather) return null;

  const { face, label } = faceFor(weather);

  return (
    <section className="card overflow-hidden">
      <div className="flex items-start justify-between gap-4 p-6">
        <div>
          <p className="card-title">Ahora</p>
          <div className="mt-2 flex items-start">
            <span className="text-7xl font-semibold leading-none tracking-tight">
              {Math.round(weather.temperature)}
            </span>
            <span className="mt-2 text-2xl font-medium text-slate-400">°C</span>
          </div>
          <p className="mt-3 text-base font-medium text-slate-700">
            {weather.condition}
          </p>
          <p className="mt-1 text-sm text-slate-400">
            Sensación {Math.round(weather.feels_like)}°C
          </p>
        </div>

        <div className="flex flex-col items-center gap-1">
          <div
            className="flex h-20 w-20 items-center justify-center rounded-full bg-slate-50 text-5xl"
            role="img"
            aria-label={label}
          >
            {face}
          </div>
          <span className="text-2xl" aria-hidden="true">
            {weather.emoji}
          </span>
        </div>
      </div>
    </section>
  );
}
