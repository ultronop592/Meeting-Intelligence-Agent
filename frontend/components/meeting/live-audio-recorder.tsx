"use client";

import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  Check,
  Disc3,
  Mic,
  MicOff,
  Pause,
  Play,
  RotateCcw,
  Sparkles,
  Square,
  Volume2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type LiveAudioRecorderProps = {
  onRecordingComplete: (file: File) => void;
  disabled?: boolean;
};

type RecorderState = "idle" | "recording" | "paused" | "stopped";

export function LiveAudioRecorder({
  onRecordingComplete,
  disabled = false,
}: LiveAudioRecorderProps) {
  const [state, setState] = useState<RecorderState>("idle");
  const [durationSeconds, setDurationSeconds] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [audioFileSizeMb, setAudioFileSizeMb] = useState<number | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      stopTracks();
      if (timerRef.current) window.clearInterval(timerRef.current);
      if (animationFrameRef.current) window.cancelAnimationFrame(animationFrameRef.current);
      if (audioContextRef.current && audioContextRef.current.state !== "closed") {
        audioContextRef.current.close().catch(() => {});
      }
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
      }
    };
  }, [audioUrl]);

  const stopTracks = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
  };

  const drawWaveform = () => {
    if (!canvasRef.current || !analyserRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const analyser = analyserRef.current;
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const render = () => {
      animationFrameRef.current = requestAnimationFrame(render);
      analyser.getByteFrequencyData(dataArray);

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const barWidth = (canvas.width / bufferLength) * 2.5;
      let x = 0;

      for (let i = 0; i < bufferLength; i++) {
        const barHeight = (dataArray[i] / 255) * (canvas.height * 0.85);

        // Gradient from accent to purple/blue
        const gradient = ctx.createLinearGradient(0, canvas.height, 0, 0);
        gradient.addColorStop(0, "rgba(59, 130, 246, 0.2)");
        gradient.addColorStop(0.5, "rgba(99, 102, 241, 0.8)");
        gradient.addColorStop(1, "rgba(168, 85, 247, 1)");

        ctx.fillStyle = gradient;
        ctx.fillRect(x, canvas.height - barHeight, barWidth, barHeight);

        x += barWidth + 1.5;
        if (x > canvas.width) break;
      }
    };

    render();
  };

  const startRecording = async () => {
    setErrorMessage(null);
    audioChunksRef.current = [];
    setDurationSeconds(0);
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
      setAudioUrl(null);
    }
    setAudioBlob(null);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;

      // Audio analysis for real-time waveform visualization
      const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const audioCtx = new AudioCtx();
      audioContextRef.current = audioCtx;
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 64;
      analyserRef.current = analyser;

      const source = audioCtx.createMediaStreamSource(stream);
      source.connect(analyser);

      // Determine best audio mimeType
      let mimeType = "audio/webm";
      if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
        mimeType = "audio/webm;codecs=opus";
      } else if (MediaRecorder.isTypeSupported("audio/mp4")) {
        mimeType = "audio/mp4";
      }

      const mediaRecorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        stopTracks();
        if (animationFrameRef.current) {
          cancelAnimationFrame(animationFrameRef.current);
          animationFrameRef.current = null;
        }

        const blob = new Blob(audioChunksRef.current, { type: mimeType });
        setAudioBlob(blob);
        const url = URL.createObjectURL(blob);
        setAudioUrl(url);
        setAudioFileSizeMb(Number((blob.size / (1024 * 1024)).toFixed(2)));
        setState("stopped");
      };

      mediaRecorder.start(250); // Emit chunks every 250ms
      setState("recording");

      // Start timer
      timerRef.current = window.setInterval(() => {
        setDurationSeconds((sec) => sec + 1);
      }, 1000);

      // Start visualizer
      drawWaveform();
    } catch (err: unknown) {
      stopTracks();
      const msg =
        err instanceof DOMException && err.name === "NotAllowedError"
          ? "Microphone access was denied. Please allow microphone permissions in your browser to record live audio."
          : err instanceof Error
          ? err.message
          : "Failed to access microphone.";
      setErrorMessage(msg);
      setState("idle");
    }
  };

  const pauseRecording = () => {
    if (mediaRecorderRef.current && state === "recording") {
      mediaRecorderRef.current.pause();
      if (timerRef.current) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
      setState("paused");
    }
  };

  const resumeRecording = () => {
    if (mediaRecorderRef.current && state === "paused") {
      mediaRecorderRef.current.resume();
      timerRef.current = window.setInterval(() => {
        setDurationSeconds((sec) => sec + 1);
      }, 1000);
      setState("recording");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && (state === "recording" || state === "paused")) {
      mediaRecorderRef.current.stop();
      if (timerRef.current) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }
  };

  const resetRecording = () => {
    stopTracks();
    if (timerRef.current) window.clearInterval(timerRef.current);
    if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
      setAudioUrl(null);
    }
    setAudioBlob(null);
    setAudioFileSizeMb(null);
    setDurationSeconds(0);
    setErrorMessage(null);
    setState("idle");
  };

  const handleSubmit = () => {
    if (!audioBlob) return;
    const ext = audioBlob.type.includes("mp4") ? "mp4" : "webm";
    const now = new Date();
    const dateStr = now.toISOString().slice(0, 10);
    const timeStr = now.toTimeString().slice(0, 5).replace(":", "");
    const fileName = `live-recording-${dateStr}-${timeStr}.${ext}`;

    const file = new File([audioBlob], fileName, { type: audioBlob.type });
    onRecordingComplete(file);
  };

  const formatTime = (totalSeconds: number) => {
    const mins = Math.floor(totalSeconds / 60);
    const secs = totalSeconds % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  return (
    <div
      id="live-audio-recorder-panel"
      className="flex flex-col justify-between rounded-2xl border border-border/80 bg-surface p-5 shadow-xs transition-all"
    >
      <div>
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div
              className={cn(
                "flex h-9 w-9 items-center justify-center rounded-xl",
                state === "recording"
                  ? "bg-red-500/10 text-red-500 animate-pulse"
                  : state === "paused"
                  ? "bg-amber-500/10 text-amber-500"
                  : state === "stopped"
                  ? "bg-emerald-500/10 text-emerald-500"
                  : "bg-accent/10 text-accent"
              )}
            >
              {state === "recording" ? (
                <Disc3 className="h-5 w-5 animate-spin" />
              ) : (
                <Mic className="h-5 w-5" />
              )}
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">
                Live Meeting Recorder
              </h3>
              <p className="text-xs text-text-secondary">
                {state === "idle" && "Capture audio directly from your microphone"}
                {state === "recording" && "Recording in progress..."}
                {state === "paused" && "Recording paused"}
                {state === "stopped" && "Recording ready to process"}
              </p>
            </div>
          </div>

          {/* Status Badge */}
          {state !== "idle" && (
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
                  state === "recording" && "bg-red-500/10 text-red-400 border border-red-500/20",
                  state === "paused" && "bg-amber-500/10 text-amber-400 border border-amber-500/20",
                  state === "stopped" && "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                )}
              >
                <span
                  className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    state === "recording" && "bg-red-500 animate-pulse",
                    state === "paused" && "bg-amber-500",
                    state === "stopped" && "bg-emerald-500"
                  )}
                />
                {state.toUpperCase()}
              </span>
              <span className="font-mono text-sm font-bold text-foreground">
                {formatTime(durationSeconds)}
              </span>
            </div>
          )}
        </div>

        {/* Error message */}
        {errorMessage && (
          <div className="mt-3 flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
            <AlertCircle className="h-4 w-4 shrink-0 text-red-400" />
            <p>{errorMessage}</p>
          </div>
        )}

        {/* Dynamic Display Area */}
        <div className="mt-4 flex min-h-[120px] flex-col items-center justify-center rounded-xl border border-dashed border-border/80 bg-surface-2/60 p-4">
          {state === "idle" && (
            <div className="text-center space-y-2">
              <p className="text-xs text-text-tertiary">
                Click below to start recording. Audio will be transcribed with Groq Whisper and analyzed by the intelligence agent.
              </p>
              <Button
                id="btn-start-recording"
                type="button"
                onClick={startRecording}
                disabled={disabled}
                className="mt-2 inline-flex items-center gap-2 bg-red-600 hover:bg-red-700 text-white font-medium"
              >
                <Mic className="h-4 w-4" />
                Start Recording
              </Button>
            </div>
          )}

          {(state === "recording" || state === "paused") && (
            <div className="w-full space-y-3">
              <canvas
                ref={canvasRef}
                width={360}
                height={60}
                className="w-full rounded-lg bg-surface/80"
              />
              <div className="flex items-center justify-center gap-3 pt-1">
                {state === "recording" ? (
                  <Button
                    id="btn-pause-recording"
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={pauseRecording}
                    className="inline-flex items-center gap-1.5"
                  >
                    <Pause className="h-3.5 w-3.5" />
                    Pause
                  </Button>
                ) : (
                  <Button
                    id="btn-resume-recording"
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={resumeRecording}
                    className="inline-flex items-center gap-1.5"
                  >
                    <Play className="h-3.5 w-3.5" />
                    Resume
                  </Button>
                )}

                <Button
                  id="btn-stop-recording"
                  type="button"
                  size="sm"
                  onClick={stopRecording}
                  className="inline-flex items-center gap-1.5 bg-red-600 hover:bg-red-700 text-white"
                >
                  <Square className="h-3.5 w-3.5" />
                  Stop Recording
                </Button>

                <Button
                  id="btn-cancel-recording"
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={resetRecording}
                  className="text-text-tertiary hover:text-foreground"
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}

          {state === "stopped" && audioUrl && (
            <div className="w-full space-y-3">
              <div className="flex items-center justify-between text-xs text-text-secondary">
                <span className="flex items-center gap-1.5">
                  <Volume2 className="h-3.5 w-3.5 text-accent" />
                  Recording Preview
                </span>
                <span>
                  {formatTime(durationSeconds)} • {audioFileSizeMb ?? 0} MB
                </span>
              </div>

              <audio
                controls
                src={audioUrl}
                className="w-full h-10 rounded-lg outline-hidden"
              />

              <div className="flex items-center justify-between gap-3 pt-2">
                <Button
                  id="btn-rerecord"
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={resetRecording}
                  disabled={disabled}
                  className="inline-flex items-center gap-1.5"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  Discard & Re-record
                </Button>

                <Button
                  id="btn-process-recording"
                  type="button"
                  size="sm"
                  onClick={handleSubmit}
                  disabled={disabled || !audioBlob}
                  className="inline-flex items-center gap-1.5 bg-accent text-white hover:opacity-90 font-medium"
                >
                  <Sparkles className="h-3.5 w-3.5" />
                  Process Meeting Audio
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between text-[11px] text-text-tertiary border-t border-border/50 pt-2.5">
        <span>Audio formats: WebM / MP4 with Opus encoding</span>
        <span>Automatic FFmpeg chunking supported</span>
      </div>
    </div>
  );
}
