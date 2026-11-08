import { useCallback, useEffect, useRef, useState } from "react";
import { useSpeech } from "../hooks/useSpeech";

export default function AssistantPanel({ answer, source, loading, onAsk }) {
  const [text, setText] = useState("");
  const lastSpoken = useRef("");

  const submitPrompt = useCallback(
    async (value) => {
      const prompt = value.trim();
      if (!prompt || loading) return;
      await onAsk(prompt);
    },
    [onAsk, loading]
  );

  const {
    supported,
    listening,
    speaking,
    error: speechError,
    start,
    stop,
    speak,
    cancelSpeech,
    unlockAudio,
  } = useSpeech({
    onResult: (transcript) => {
      setText(transcript);
      submitPrompt(transcript);
    },
  });

  useEffect(() => {
    if (answer && answer !== lastSpoken.current) {
      lastSpoken.current = answer;
      speak(answer);
    }
  }, [answer, speak]);

  function handleSubmit(event) {
    event.preventDefault();
    unlockAudio();
    submitPrompt(text);
    setText("");
  }

  function handleMicClick() {
    unlockAudio();
    if (listening) {
      stop();
    } else {
      start();
    }
  }

  return (
    <section className="card p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="card-title">Asistente</p>
          <p className="mt-1 text-sm font-medium text-slate-800">
            Pregunta por voz o texto
          </p>
        </div>
        <span className="text-xl" aria-hidden="true">
          🎙️
        </span>
      </div>

      <form onSubmit={handleSubmit} className="mt-3 flex items-center gap-2">
        <input
          type="text"
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="¿Necesito paraguas hoy?"
          className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-800 outline-none placeholder:text-slate-400 focus:border-slate-400"
        />

        <button
          type="button"
          onClick={handleMicClick}
          disabled={!supported || loading}
          className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full border transition-colors ${
            listening
              ? "border-rose-200 bg-rose-50 text-rose-600"
              : "border-slate-200 bg-white text-slate-700 active:bg-slate-100"
          } disabled:cursor-not-allowed disabled:opacity-40`}
          aria-label={listening ? "Detener micrófono" : "Usar micrófono"}
          title={supported ? "Hablar" : "Reconocimiento de voz no disponible"}
        >
          <svg
            viewBox="0 0 24 24"
            className="h-5 w-5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 4a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V7a3 3 0 0 0-3-3Z"
            />
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M5 11a7 7 0 0 0 14 0M12 18v3"
            />
          </svg>
        </button>

        <button
          type="submit"
          disabled={loading || !text.trim()}
          className="btn btn-primary h-11 w-11 shrink-0 px-0"
          aria-label="Enviar pregunta"
        >
          <svg
            viewBox="0 0 24 24"
            className="h-5 w-5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M4 12h15m0 0-6-6m6 6-6 6"
            />
          </svg>
        </button>
      </form>

      {!supported && (
        <p className="mt-2 text-[11px] text-slate-400">
          El micrófono no está disponible en este navegador. Usa HTTPS en Safari iOS.
        </p>
      )}
      {speechError && <p className="mt-2 text-xs text-rose-600">{speechError}</p>}
      {listening && (
        <p className="mt-2 text-xs font-medium text-rose-600">Escuchando…</p>
      )}

      {(loading || answer) && (
        <div className="mt-4 rounded-xl bg-slate-50 p-3">
          {loading ? (
            <div className="space-y-2">
              <div className="h-3 w-4/5 animate-pulse rounded bg-slate-200" />
              <div className="h-3 w-3/5 animate-pulse rounded bg-slate-200" />
            </div>
          ) : (
            <>
              <div className="flex items-start gap-2">
                <span className="mt-0.5 text-sm" aria-hidden="true">
                  🤖
                </span>
                <p className="text-sm leading-relaxed text-slate-700">{answer}</p>
              </div>
              <div className="mt-2 flex items-center justify-between gap-2">
                <span className="text-[10px] font-medium uppercase tracking-wide text-slate-400">
                  {source === "gemini" ? "Gemini" : "Razonador local"}
                </span>
                {speaking && (
                  <button
                    type="button"
                    onClick={cancelSpeech}
                    className="text-[11px] font-medium text-slate-500 underline"
                  >
                    Detener voz
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}
