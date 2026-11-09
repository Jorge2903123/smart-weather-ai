import { useCallback, useEffect, useMemo, useState } from "react";
import { cleanupLogs, getAdminHistory, getAdminSummary } from "../services/api";

const QUERY_TYPES = {
  assistant_query: "Asistente",
  vision: "Visión",
  weather_check: "Clima (legado)",
  destination_query: "Destino (legado)",
};

function formatDay(value) {
  if (!value) return "—";
  const date = new Date(`${value}T12:00:00`);
  return date.toLocaleDateString("es-MX", {
    weekday: "short",
    day: "2-digit",
    month: "short",
  });
}

function formatDateTime(value) {
  if (!value) return "—";
  return new Date(value).toLocaleString("es-MX", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function StatCard({ label, value, hint }) {
  return (
    <div className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-3">
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
        {label}
      </p>
      <p className="mt-1 text-xl font-semibold text-slate-800">{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-slate-400">{hint}</p>}
    </div>
  );
}

export default function AdminPanel({ token }) {
  const [summary, setSummary] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [cleaning, setCleaning] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextSummary, nextHistory] = await Promise.all([
        getAdminSummary(token),
        getAdminHistory(50, token),
      ]);
      setSummary(nextSummary);
      setHistory(nextHistory.items ?? []);
    } catch (err) {
      setError(
        err.status === 401 || err.status === 403
          ? "Token de administrador inválido. Cierra y vuelve a ingresarlo."
          : err.message
      );
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  const handleCleanup = useCallback(async () => {
    const confirmed = window.confirm(
      "Se eliminarán registros pasivos antiguos y duplicados. ¿Continuar?"
    );
    if (!confirmed) return;

    setCleaning(true);
    setError("");
    try {
      await cleanupLogs(token);
      await load();
    } catch (err) {
      setError(
        err.status === 401 || err.status === 403
          ? "Token de administrador inválido. Cierra y vuelve a ingresarlo."
          : err.message
      );
    } finally {
      setCleaning(false);
    }
  }, [load, token]);

  const wettest = useMemo(() => summary?.wettest_days?.[0], [summary]);

  return (
    <div className="mt-3 space-y-3">
      <section className="card p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="card-title">Métricas</p>
            <p className="mt-1 text-sm font-medium text-slate-800">
              Acumulado día con día
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="btn px-3 py-2 text-xs"
              onClick={handleCleanup}
              disabled={cleaning}
            >
              {cleaning ? "Limpiando…" : "Limpiar"}
            </button>
            <button type="button" className="btn px-3 py-2 text-xs" onClick={load}>
              Actualizar
            </button>
          </div>
        </div>

        {error && <p className="mt-3 text-xs text-rose-600">{error}</p>}

        {loading && !summary ? (
          <div className="mt-4 grid grid-cols-2 gap-2">
            {[0, 1, 2, 3].map((item) => (
              <div
                key={item}
                className="h-20 animate-pulse rounded-xl bg-slate-100"
              />
            ))}
          </div>
        ) : (
          summary && (
            <>
              <div className="mt-4 grid grid-cols-2 gap-2">
                <StatCard
                  label="Consultas totales"
                  value={summary.total_logs}
                />
                <StatCard
                  label="Días con datos"
                  value={summary.days?.length ?? 0}
                />
                <StatCard
                  label="Temp. prom. reciente"
                  value={
                    summary.days?.[0]?.avg_temperature != null
                      ? `${summary.days[0].avg_temperature}°C`
                      : "—"
                  }
                />
                <StatCard
                  label="Día más lluvioso"
                  value={wettest ? formatDay(wettest.date) : "—"}
                  hint={
                    wettest
                      ? `${wettest.max_rain_probability}% lluvia máx.`
                      : undefined
                  }
                />
              </div>

              <div className="mt-4">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                  Por día
                </p>
                <div className="mt-2 overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="text-[10px] uppercase tracking-wide text-slate-400">
                        <th className="py-1.5 pr-2 font-medium">Día</th>
                        <th className="py-1.5 pr-2 font-medium">Consultas</th>
                        <th className="py-1.5 pr-2 font-medium">Temp. prom.</th>
                        <th className="py-1.5 font-medium">Lluvia máx.</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {(summary.days ?? []).map((day) => (
                        <tr key={day.date} className="text-slate-600">
                          <td className="py-2 pr-2 font-medium text-slate-800">
                            {formatDay(day.date)}
                          </td>
                          <td className="py-2 pr-2">{day.queries}</td>
                          <td className="py-2 pr-2">
                            {day.avg_temperature != null
                              ? `${day.avg_temperature}°C`
                              : "—"}
                          </td>
                          <td className="py-2">
                            {Math.round(day.max_rain_probability)}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )
        )}
      </section>

      <section className="card p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="card-title">Historial reciente</p>
            <p className="mt-1 text-sm font-medium text-slate-800">
              Últimas consultas registradas
            </p>
          </div>
          <span className="text-xl" aria-hidden="true">
            🗂️
          </span>
        </div>

        {loading && !history.length ? (
          <div className="mt-4 space-y-2">
            {[0, 1, 2].map((row) => (
              <div
                key={row}
                className="h-10 animate-pulse rounded-xl bg-slate-100"
              />
            ))}
          </div>
        ) : history.length === 0 ? (
          <p className="mt-3 text-xs text-slate-400">
            Aún no hay consultas registradas.
          </p>
        ) : (
          <ul className="mt-3 divide-y divide-slate-100">
            {history.map((item) => (
              <li key={item.id} className="flex items-start gap-3 py-2.5 text-xs">
                <span className="w-20 shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-center text-[10px] font-semibold text-slate-500">
                  {QUERY_TYPES[item.query_type] ?? item.query_type}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-slate-800">
                    {item.location}
                  </p>
                  <p className="mt-0.5 text-slate-400">
                    {item.sky_condition}
                    {item.temperature != null
                      ? ` · ${item.temperature}°C`
                      : ""}
                    {` · ${Math.round(item.rain_probability)}% lluvia`}
                  </p>
                </div>
                <span className="shrink-0 text-slate-400">
                  {formatDateTime(item.created_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
