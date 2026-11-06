import { useState } from "react";

function Metric({ label, value }) {
  return (
    <div className="rounded-xl bg-slate-50 px-3 py-2.5">
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
        {label}
      </p>
      <p className="mt-0.5 text-sm font-semibold text-slate-700">{value}</p>
    </div>
  );
}

export default function ForecastSection({ forecast, weather, loading }) {
  const [open, setOpen] = useState(false);
  const points = forecast?.points ?? [];

  return (
    <section className="card p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="card-title">Pronóstico</p>
          <p className="mt-1 text-sm font-medium text-slate-800">
            Próximas {points.length || 6} horas
          </p>
        </div>

        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="btn px-3 py-2 text-xs"
          aria-expanded={open}
        >
          {open ? "Ocultar" : "Ver detalles"}
          <svg
            viewBox="0 0 24 24"
            className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`}
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            aria-hidden="true"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="m6 9 6 6 6-6" />
          </svg>
        </button>
      </div>

      {open && (
        <div className="mt-4 space-y-4">
          {weather && (
            <div className="grid grid-cols-3 gap-2">
              <Metric label="Humedad" value={`${weather.humidity}%`} />
              <Metric label="Viento" value={`${weather.wind_kph} km/h`} />
              <Metric
                label="Sensación"
                value={`${Math.round(weather.feels_like)}°C`}
              />
            </div>
          )}

          {loading && !points.length ? (
            <div className="space-y-2">
              {[0, 1, 2].map((row) => (
                <div
                  key={row}
                  className="h-11 animate-pulse rounded-xl bg-slate-100"
                />
              ))}
            </div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {points.map((point) => (
                <li
                  key={point.time}
                  className="flex items-center gap-3 py-2.5 text-sm"
                >
                  <span className="w-12 shrink-0 font-medium text-slate-500">
                    {point.time}
                  </span>
                  <span className="w-14 shrink-0 font-semibold text-slate-800">
                    {Math.round(point.temperature)}°C
                  </span>
                  <div className="flex flex-1 items-center gap-2">
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                      <div
                        className="h-full rounded-full bg-sky-400"
                        style={{ width: `${point.rain_probability}%` }}
                      />
                    </div>
                    <span className="w-10 shrink-0 text-right text-xs text-slate-400">
                      {point.rain_probability}%
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}

          <p className="text-[11px] leading-relaxed text-slate-400">
            Fuente: {forecast?.source === "lstm" ? "modelo LSTM" : "modelo simulado"}.
            Datos de demostración para el MVP.
          </p>
        </div>
      )}
    </section>
  );
}
