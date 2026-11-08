import { useEffect, useState } from "react";

function formatTime(date) {
  return date.toLocaleTimeString("es-MX", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function Header({
  location,
  hint,
  updatedAt,
  online = true,
  showGpsButton = false,
  gpsLoading = false,
  onRequestGps,
  onOpenAdmin,
}) {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30000);
    return () => clearInterval(id);
  }, []);

  return (
    <header className="flex items-start justify-between gap-4 px-1 pb-2">
      <div className="min-w-0">
        <div className="flex items-center gap-1.5 text-slate-500">
          <svg
            viewBox="0 0 24 24"
            className="h-4 w-4 shrink-0"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 21s7-5.1 7-11a7 7 0 1 0-14 0c0 5.9 7 11 7 11Z"
            />
            <circle cx="12" cy="10" r="2.4" />
          </svg>
          <p className="min-w-0 truncate text-sm font-medium">
            {location || "Mi ubicación"}
          </p>
          {showGpsButton && (
            <button
              type="button"
              onClick={onRequestGps}
              disabled={gpsLoading}
              title="Usar GPS preciso"
              aria-label="Actualizar ubicación con GPS preciso"
              className="ml-1 flex shrink-0 items-center gap-1 rounded-full border border-slate-200 bg-white px-1.5 py-0.5 text-[10px] font-semibold text-slate-500 transition hover:border-sky-200 hover:text-sky-600 disabled:cursor-wait disabled:opacity-60"
            >
              <svg
                viewBox="0 0 24 24"
                className={`h-3.5 w-3.5 ${gpsLoading ? "animate-pulse" : ""}`}
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                aria-hidden="true"
              >
                <circle cx="12" cy="12" r="3" />
                <path
                  strokeLinecap="round"
                  d="M12 2v3M12 19v3M2 12h3M19 12h3"
                />
              </svg>
              {gpsLoading ? "GPS…" : "GPS"}
            </button>
          )}
        </div>
        <p className="mt-0.5 text-xs text-slate-400">
          {formatTime(now)}
          {updatedAt ? ` · Act. ${formatTime(new Date(updatedAt))}` : ""}
          {hint ? ` · ${hint}` : ""}
        </p>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        {onOpenAdmin && (
          <button
            type="button"
            onClick={onOpenAdmin}
            title="Panel de administración"
            aria-label="Abrir panel de administración"
            className="flex h-7 w-7 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-400 transition hover:border-slate-300 hover:text-slate-700"
          >
            <svg
              viewBox="0 0 24 24"
              className="h-3.5 w-3.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              aria-hidden="true"
            >
              <rect x="4" y="10" width="16" height="10" rx="2" />
              <path
                strokeLinecap="round"
                d="M8 10V7a4 4 0 0 1 8 0v3"
              />
            </svg>
          </button>
        )}

        <div
          className={`flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium ${
            online
              ? "border-emerald-200 bg-emerald-50 text-emerald-700"
              : "border-rose-200 bg-rose-50 text-rose-700"
          }`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              online ? "bg-emerald-500" : "bg-rose-500"
            }`}
          />
          {online ? "En vivo" : "Sin conexión"}
        </div>
      </div>
    </header>
  );
}
