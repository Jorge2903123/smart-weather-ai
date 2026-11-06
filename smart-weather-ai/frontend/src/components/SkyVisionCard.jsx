import { useEffect, useRef, useState } from "react";
import { analyzeSky } from "../services/api";

export default function SkyVisionCard({ analysis, onAnalyzed }) {
  const inputRef = useRef(null);
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview);
    };
  }, [preview]);

  async function handleFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;

    setError("");
    setPreview(URL.createObjectURL(file));
    setLoading(true);

    try {
      const result = await analyzeSky(file);
      onAnalyzed?.(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      event.target.value = "";
    }
  }

  return (
    <section className="card p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="card-title">Visión del cielo</p>
          <p className="mt-1 text-sm font-medium text-slate-800">
            Analiza una foto con la CNN
          </p>
        </div>
        <span className="text-xl" aria-hidden="true">
          📷
        </span>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={handleFile}
      />

      <button
        type="button"
        className="btn mt-3 w-full"
        onClick={() => inputRef.current?.click()}
        disabled={loading}
      >
        {loading ? "Analizando imagen..." : "Tomar o subir foto del cielo"}
      </button>

      {error && <p className="mt-3 text-xs text-rose-600">{error}</p>}

      {(preview || analysis) && (
        <div className="mt-4 flex items-center gap-3 rounded-xl border border-slate-100 bg-slate-50 p-3">
          {preview && (
            <img
              src={preview}
              alt="Cielo capturado"
              className="h-16 w-16 shrink-0 rounded-lg object-cover"
            />
          )}
          <div className="min-w-0 flex-1">
            {loading ? (
              <div className="space-y-2">
                <div className="h-3 w-24 animate-pulse rounded bg-slate-200" />
                <div className="h-3 w-16 animate-pulse rounded bg-slate-200" />
              </div>
            ) : (
              analysis && (
                <>
                  <p className="truncate text-sm font-semibold text-slate-800">
                    {analysis.label}
                  </p>
                  <p className="text-xs text-slate-500">{analysis.state}</p>
                  <div className="mt-2 flex items-center gap-2">
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200">
                      <div
                        className="h-full rounded-full bg-slate-700"
                        style={{ width: `${Math.round(analysis.confidence * 100)}%` }}
                      />
                    </div>
                    <span className="text-[11px] font-medium text-slate-500">
                      {Math.round(analysis.confidence * 100)}%
                    </span>
                  </div>
                </>
              )
            )}
          </div>
        </div>
      )}

      <p className="mt-3 text-[11px] leading-relaxed text-slate-400">
        La imagen se procesa en 224×224 px. Si aún no hay pesos entrenados, se usa
        el clasificador de respaldo.
      </p>
    </section>
  );
}
