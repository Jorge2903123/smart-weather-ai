import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Hook para Web Speech API.
 *
 * - `start()` / `stop()`: reconocimiento de voz (micrófono).
 * - `speak(text)`: síntesis de voz nativa.
 * - `onResult`: callback que recibe la transcripción final y permite enviarla
 *   automáticamente al asistente.
 *
 * Nota iOS/Safari: el micrófono solo funciona en HTTPS (o localhost). Para
 * probar desde el iPhone usa un túnel Cloudflare/Ngrok o configura HTTPS.
 */
export function useSpeech({ onResult, lang = "es-MX" } = {}) {
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [error, setError] = useState("");

  const recognitionRef = useRef(null);
  const onResultRef = useRef(onResult);

  useEffect(() => {
    onResultRef.current = onResult;
  }, [onResult]);

  useEffect(() => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setSupported(false);
      return undefined;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = lang;
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      setError("");
      setListening(true);
    };

    recognition.onresult = (event) => {
      const text = event.results?.[0]?.[0]?.transcript?.trim();
      if (text) onResultRef.current?.(text);
    };

    recognition.onerror = (event) => {
      if (event.error === "not-allowed") {
        setError("Permiso de micrófono denegado. Revisa los ajustes de Safari.");
      } else if (event.error === "no-speech") {
        setError("No se detectó voz. Intenta de nuevo.");
      } else if (event.error !== "aborted") {
        setError("No se pudo usar el micrófono.");
      }
      setListening(false);
    };

    recognition.onend = () => setListening(false);

    recognitionRef.current = recognition;
    setSupported(true);

    return () => {
      recognition.onresult = null;
      recognition.onerror = null;
      recognition.onend = null;
      try {
        recognition.abort();
      } catch {
        /* noop */
      }
    };
  }, [lang]);

  const start = useCallback(() => {
    if (!recognitionRef.current) return;
    setError("");
    try {
      recognitionRef.current.start();
    } catch {
      // Safari lanza error si se llama start() mientras ya está activo.
    }
  }, []);

  const stop = useCallback(() => {
    try {
      recognitionRef.current?.stop();
    } catch {
      /* noop */
    }
  }, []);

  const speak = useCallback(
    (text) => {
      if (!text || !("speechSynthesis" in window)) return;
      window.speechSynthesis.cancel();

      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = lang;
      utterance.rate = 1;
      utterance.pitch = 1;
      utterance.onstart = () => setSpeaking(true);
      utterance.onend = () => setSpeaking(false);
      utterance.onerror = () => setSpeaking(false);

      window.speechSynthesis.speak(utterance);
    },
    [lang]
  );

  const cancelSpeech = useCallback(() => {
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    setSpeaking(false);
  }, []);

  return {
    supported,
    listening,
    speaking,
    error,
    start,
    stop,
    speak,
    cancelSpeech,
  };
}
