import { useEffect, useRef, useState } from "react";
import AdminPanel from "./AdminPanel";
import { getAdminSummary } from "../services/api";

export default function AdminModal({ open, onClose }) {
  const [tokenInput, setTokenInput] = useState("");
  const [token, setToken] = useState("");
  const [authorized, setAuthorized] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");
  const requestRef = useRef(0);

  useEffect(() => {
    requestRef.current += 1;
    setTokenInput("");
    setToken("");
    setAuthorized(false);
    setChecking(false);
    setError("");
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  async function handleSubmit(event) {
    event.preventDefault();
    const candidate = tokenInput.trim();
    if (!candidate) {
      setError("PIN incorrecto.");
      return;
    }

    const requestId = requestRef.current + 1;
    requestRef.current = requestId;
    setChecking(true);
    setError("");
    try {
      await getAdminSummary(candidate);
      if (requestRef.current !== requestId) return;
      setToken(candidate);
      setAuthorized(true);
    } catch (err) {
      if (requestRef.current !== requestId) return;
      setError(
        err.status === 401 || err.status === 403
          ? "PIN incorrecto."
          : err.message
      );
    } finally {
      if (requestRef.current === requestId) setChecking(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Panel de administración"
    >
      <div className="safe-bottom max-h-[90dvh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-slate-200 bg-skysoft p-4 shadow-xl">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xl" aria-hidden="true">
              🔒
            </span>
            <div>
              <p className="text-sm font-semibold text-slate-800">
                Administración
              </p>
              <p className="text-[11px] text-slate-400">
                Historial y métricas acumuladas
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 transition hover:text-slate-800"
            aria-label="Cerrar administración"
          >
            <svg
              viewBox="0 0 24 24"
              className="h-4 w-4"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              aria-hidden="true"
            >
              <path strokeLinecap="round" d="M6 6l12 12M18 6 6 18" />
            </svg>
          </button>
        </div>

        {authorized ? (
          <AdminPanel token={token} />
        ) : (
          <form
            onSubmit={handleSubmit}
            className="mx-auto mt-6 max-w-xs space-y-3"
          >
            <p className="text-center text-xs text-slate-500">
              Introduce el PIN o token para acceder al historial.
            </p>
            <input
              type="password"
              autoFocus
              autoCapitalize="off"
              autoCorrect="off"
              spellCheck={false}
              value={tokenInput}
              onChange={(event) => setTokenInput(event.target.value)}
              placeholder="PIN o token de administrador"
              className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-center text-sm text-slate-800 outline-none placeholder:text-slate-400 focus:border-slate-400"
            />
            {error && (
              <p className="text-center text-xs text-rose-600">{error}</p>
            )}
            <button
              type="submit"
              disabled={checking}
              className="btn btn-primary w-full disabled:opacity-60"
            >
              {checking ? "Verificando…" : "Ingresar"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
