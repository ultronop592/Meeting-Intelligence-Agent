"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { transcribeLiveChunk } from "@/lib/api/meetings";

export type TranscriptionEngine = "web-speech" | "server-stream" | "none";

export type UseLiveTranscriptionOptions = {
  language?: string;
  onTranscriptUpdate?: (fullTranscript: string, isFinal: boolean) => void;
  onError?: (errorMsg: string) => void;
};

// Web Speech API interface declarations for TypeScript compatibility
interface SpeechRecognitionResultItem {
  transcript: string;
  confidence: number;
}

interface SpeechRecognitionResultLike {
  isFinal: boolean;
  length: number;
  item(index: number): SpeechRecognitionResultItem;
  [index: number]: SpeechRecognitionResultItem;
}

interface SpeechRecognitionResultListLike {
  length: number;
  item(index: number): SpeechRecognitionResultLike;
  [index: number]: SpeechRecognitionResultLike;
}

interface SpeechRecognitionEventLike extends Event {
  resultIndex: number;
  results: SpeechRecognitionResultListLike;
}

interface SpeechRecognitionErrorEventLike extends Event {
  error: string;
  message?: string;
}

interface SpeechRecognitionInstance extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onstart: ((this: SpeechRecognitionInstance, ev: Event) => void) | null;
  onend: ((this: SpeechRecognitionInstance, ev: Event) => void) | null;
  onerror: ((this: SpeechRecognitionInstance, ev: SpeechRecognitionErrorEventLike) => void) | null;
  onresult: ((this: SpeechRecognitionInstance, ev: SpeechRecognitionEventLike) => void) | null;
}

declare global {
  interface Window {
    SpeechRecognition?: new () => SpeechRecognitionInstance;
    webkitSpeechRecognition?: new () => SpeechRecognitionInstance;
  }
}

export function useLiveTranscription({
  language = "en-US",
  onTranscriptUpdate,
  onError,
}: UseLiveTranscriptionOptions = {}) {
  const [transcript, setTranscript] = useState<string>("");
  const [interimText, setInterimText] = useState<string>("");
  const [isListening, setIsListening] = useState<boolean>(false);
  const [isPaused, setIsPaused] = useState<boolean>(false);
  const [engine, setEngine] = useState<TranscriptionEngine>("none");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const isActiveRef = useRef<boolean>(false);
  const isPausedRef = useRef<boolean>(false);
  const finalTranscriptRef = useRef<string>("");
  const isProcessingChunkRef = useRef<boolean>(false);

  // Check browser capability on mount
  useEffect(() => {
    if (typeof window !== "undefined") {
      const SpeechRecognitionCtor =
        window.SpeechRecognition || window.webkitSpeechRecognition;
      if (SpeechRecognitionCtor) {
        setEngine("web-speech");
      } else {
        setEngine("server-stream");
      }
    }
  }, []);

  const calculateWordCount = (text: string) => {
    const trimmed = text.trim();
    return trimmed ? trimmed.split(/\s+/).length : 0;
  };

  const getFullTranscript = useCallback(() => {
    const finalPart = finalTranscriptRef.current.trim();
    const interimPart = interimText.trim();
    if (finalPart && interimPart) {
      return `${finalPart} ${interimPart}`;
    }
    return finalPart || interimPart || "";
  }, [interimText]);

  // Start continuous Web Speech listening
  const startListening = useCallback(() => {
    setErrorMessage(null);
    finalTranscriptRef.current = "";
    setTranscript("");
    setInterimText("");
    isActiveRef.current = true;
    isPausedRef.current = false;
    setIsPaused(false);

    if (typeof window === "undefined") return;

    const SpeechRecognitionCtor =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognitionCtor) {
      // Fallback to server chunking mode
      setEngine("server-stream");
      setIsListening(true);
      return;
    }

    try {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {}
      }

      const recognition = new SpeechRecognitionCtor();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = language;
      recognition.maxAlternatives = 1;

      recognition.onstart = () => {
        setIsListening(true);
        setEngine("web-speech");
      };

      recognition.onresult = (event: SpeechRecognitionEventLike) => {
        if (!isActiveRef.current || isPausedRef.current) return;

        let interimAccumulator = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const result = event.results[i];
          const text = result[0]?.transcript || "";
          if (result.isFinal) {
            const formatted = text.trim();
            if (formatted) {
              finalTranscriptRef.current = finalTranscriptRef.current
                ? `${finalTranscriptRef.current} ${formatted}`
                : formatted;
              setTranscript(finalTranscriptRef.current);
            }
          } else {
            interimAccumulator += text;
          }
        }

        const trimmedInterim = interimAccumulator.trim();
        setInterimText(trimmedInterim);

        const currentFull = finalTranscriptRef.current
          ? (trimmedInterim ? `${finalTranscriptRef.current} ${trimmedInterim}` : finalTranscriptRef.current)
          : trimmedInterim;

        if (onTranscriptUpdate) {
          onTranscriptUpdate(currentFull, trimmedInterim.length === 0);
        }
      };

      recognition.onerror = (event: SpeechRecognitionErrorEventLike) => {
        // "no-speech" is common when speakers pause, ignore and allow continuous listening
        if (event.error === "no-speech") {
          return;
        }

        if (event.error === "not-allowed" || event.error === "service-not-allowed") {
          const msg = "Speech recognition permission denied by browser.";
          setErrorMessage(msg);
          onError?.(msg);
          setIsListening(false);
          isActiveRef.current = false;
          return;
        }

        // Network or other transient error: switch gracefully to server stream mode
        if (event.error === "network") {
          setEngine("server-stream");
        }
      };

      recognition.onend = () => {
        // Continuous listening auto-restart if still actively recording and not paused
        if (isActiveRef.current && !isPausedRef.current) {
          try {
            recognition.start();
          } catch {
            // Already started or restarting
          }
        } else if (!isActiveRef.current) {
          setIsListening(false);
        }
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to initialize live speech recognition.";
      setErrorMessage(msg);
      setEngine("server-stream");
      setIsListening(true);
    }
  }, [language, onError, onTranscriptUpdate]);

  const pauseListening = useCallback(() => {
    isPausedRef.current = true;
    setIsPaused(true);
    setInterimText("");
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {}
    }
  }, []);

  const resumeListening = useCallback(() => {
    isPausedRef.current = false;
    setIsPaused(false);
    if (isActiveRef.current && recognitionRef.current) {
      try {
        recognitionRef.current.start();
      } catch {}
    }
  }, []);

  const stopListening = useCallback((): string => {
    isActiveRef.current = false;
    isPausedRef.current = false;
    setIsListening(false);
    setIsPaused(false);
    setInterimText("");

    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {}
      recognitionRef.current = null;
    }

    const finalResult = finalTranscriptRef.current.trim();
    return finalResult;
  }, []);

  const clearTranscript = useCallback(() => {
    finalTranscriptRef.current = "";
    setTranscript("");
    setInterimText("");
  }, []);

  // Process live audio chunk via backend Groq Whisper (fallback or periodic sync)
  const processAudioChunk = useCallback(
    async (chunkBlob: Blob, filename = "live-chunk.webm") => {
      if (!isActiveRef.current || isPausedRef.current) return;
      if (chunkBlob.size < 1000) return; // Skip tiny silence chunks
      if (isProcessingChunkRef.current) return;

      isProcessingChunkRef.current = true;
      try {
        const response = await transcribeLiveChunk(
          chunkBlob,
          filename,
          finalTranscriptRef.current.slice(-150)
        );

        if (response?.text) {
          const cleanText = response.text.trim();
          if (cleanText) {
            finalTranscriptRef.current = finalTranscriptRef.current
              ? `${finalTranscriptRef.current} ${cleanText}`
              : cleanText;
            setTranscript(finalTranscriptRef.current);
            setInterimText("");
            onTranscriptUpdate?.(finalTranscriptRef.current, true);
          }
        }
      } catch (err) {
        // Silently log chunk transcription error without disrupting recording
        console.warn("Live chunk transcription error:", err);
      } finally {
        isProcessingChunkRef.current = false;
      }
    },
    [onTranscriptUpdate]
  );

  // Clean up on component unmount
  useEffect(() => {
    return () => {
      isActiveRef.current = false;
      isPausedRef.current = false;
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {}
        recognitionRef.current = null;
      }
    };
  }, []);

  const fullTranscript = getFullTranscript();
  const wordCount = calculateWordCount(fullTranscript);

  return {
    transcript,
    interimText,
    fullTranscript,
    wordCount,
    isListening,
    isPaused,
    engine,
    errorMessage,
    isSupported: engine !== "none",
    startListening,
    stopListening,
    pauseListening,
    resumeListening,
    clearTranscript,
    processAudioChunk,
  };
}
