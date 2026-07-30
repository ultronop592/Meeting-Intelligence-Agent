"use client";

import { useEffect, useRef, useState } from "react";
import { Play, Pause, Volume2, VolumeX, RotateCcw, FastForward, User } from "lucide-react";
import { Button } from "@/components/ui/button";

interface AudioPlayerProps {
  audioUrl: string;
  diarizedTranscript?: string | null;
  plainTranscript?: string | null;
}

interface TranscriptLine {
  id: number;
  speaker: string;
  text: string;
  approxStartSeconds: number;
}

export function AudioPlayer({ audioUrl, diarizedTranscript, plainTranscript }: AudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  const [hasError, setHasError] = useState(false);

  // Parse lines into structured paragraphs with estimated start times
  const lines: TranscriptLine[] = (diarizedTranscript || plainTranscript || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, idx, totalLines) => {
      let speaker = "Speaker";
      let text = line;

      // Extract SPEAKER_XX or Name: prefix if present
      const match = line.match(/^([A-Za-z0-9_ -]+):\s*(.*)$/);
      if (match) {
        speaker = match[1];
        text = match[2];
      }

      // Estimate timestamp based on paragraph index vs total audio duration
      const totalCount = totalLines.length || 1;
      const approxStartSeconds = duration > 0 ? (idx / totalCount) * duration : idx * 10;

      return {
        id: idx,
        speaker,
        text,
        approxStartSeconds,
      };
    });

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const onTimeUpdate = () => setCurrentTime(audio.currentTime);
    const onLoadedMetadata = () => setDuration(audio.duration);
    const onEnded = () => setIsPlaying(false);
    const onError = () => setHasError(true);

    audio.addEventListener("timeupdate", onTimeUpdate);
    audio.addEventListener("loadedmetadata", onLoadedMetadata);
    audio.addEventListener("ended", onEnded);
    audio.addEventListener("error", onError);

    return () => {
      audio.removeEventListener("timeupdate", onTimeUpdate);
      audio.removeEventListener("loadedmetadata", onLoadedMetadata);
      audio.removeEventListener("ended", onEnded);
      audio.removeEventListener("error", onError);
    };
  }, []);

  const togglePlay = () => {
    if (!audioRef.current || hasError) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.play().then(() => setIsPlaying(true)).catch(() => setHasError(true));
    }
  };

  const handleSeek = (time: number) => {
    if (!audioRef.current) return;
    audioRef.current.currentTime = time;
    setCurrentTime(time);
  };

  const changeSpeed = (rate: number) => {
    setPlaybackRate(rate);
    if (audioRef.current) {
      audioRef.current.playbackRate = rate;
    }
  };

  const toggleMute = () => {
    if (!audioRef.current) return;
    audioRef.current.muted = !isMuted;
    setIsMuted(!isMuted);
  };

  const formatTime = (seconds: number) => {
    if (isNaN(seconds) || seconds < 0) return "00:00";
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  // Find currently active transcript line
  const activeLineIndex = lines.findIndex((line, i) => {
    const nextLine = lines[i + 1];
    const nextStart = nextLine ? nextLine.approxStartSeconds : duration || Infinity;
    return currentTime >= line.approxStartSeconds && currentTime < nextStart;
  });

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/90 p-5 shadow-xl backdrop-blur-sm">
      <audio ref={audioRef} src={audioUrl} preload="metadata" />

      <div className="flex flex-col gap-4">
        {/* Top Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="relative flex h-3 w-3">
              {isPlaying && (
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-400 opacity-75" />
              )}
              <span className={`relative inline-flex h-3 w-3 rounded-full ${isPlaying ? "bg-cyan-500" : "bg-slate-600"}`} />
            </span>
            <h3 className="font-semibold text-slate-100">Audio Playback & Transcript Sync</h3>
          </div>
          <span className="text-xs text-slate-400 font-mono">
            {formatTime(currentTime)} / {formatTime(duration)}
          </span>
        </div>

        {/* Scrubber / Range Bar */}
        <div className="relative flex items-center">
          <input
            type="range"
            min={0}
            max={duration || 100}
            value={currentTime}
            onChange={(e) => handleSeek(Number(e.target.value))}
            className="h-2 w-full cursor-pointer appearance-none rounded-lg bg-slate-800 accent-cyan-500 focus:outline-none"
          />
        </div>

        {/* Controls Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={togglePlay}
              disabled={hasError}
              className="h-9 px-4 bg-cyan-500/10 border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/20 hover:text-cyan-300"
            >
              {isPlaying ? <Pause className="h-4 w-4 mr-1.5" /> : <Play className="h-4 w-4 mr-1.5 fill-current" />}
              {isPlaying ? "Pause" : "Play Audio"}
            </Button>

            <Button
              variant="ghost"
              size="sm"
              onClick={() => handleSeek(Math.max(0, currentTime - 10))}
              className="h-8 w-8 p-0 text-slate-400 hover:text-slate-200"
              title="Rewind 10s"
            >
              <RotateCcw className="h-4 w-4" />
            </Button>

            <Button
              variant="ghost"
              size="sm"
              onClick={() => handleSeek(Math.min(duration, currentTime + 10))}
              className="h-8 w-8 p-0 text-slate-400 hover:text-slate-200"
              title="Forward 10s"
            >
              <FastForward className="h-4 w-4" />
            </Button>
          </div>

          {/* Speed Selector */}
          <div className="flex items-center gap-1 rounded-lg border border-slate-800 bg-slate-950/60 p-1">
            {[0.75, 1.0, 1.25, 1.5, 2.0].map((rate) => (
              <button
                key={rate}
                onClick={() => changeSpeed(rate)}
                className={`rounded px-2 py-0.5 text-xs font-mono transition-colors ${
                  playbackRate === rate
                    ? "bg-cyan-500/20 text-cyan-400 font-bold"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {rate}x
              </button>
            ))}
          </div>

          {/* Volume Button */}
          <Button
            variant="ghost"
            size="sm"
            onClick={toggleMute}
            className="h-8 w-8 p-0 text-slate-400 hover:text-slate-200"
          >
            {isMuted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
          </Button>
        </div>

        {hasError && (
          <p className="text-xs text-amber-400/90 italic">
            Audio stream unavailable on disk. Displaying static transcript below.
          </p>
        )}

        {/* Synchronized Interactive Transcript */}
        {lines.length > 0 && (
          <div className="mt-3 max-h-72 overflow-y-auto rounded-lg border border-slate-800/80 bg-slate-950/80 p-4 space-y-2.5 scrollbar-thin">
            {lines.map((line, idx) => {
              const isActive = idx === activeLineIndex;
              return (
                <div
                  key={line.id}
                  onClick={() => handleSeek(line.approxStartSeconds)}
                  className={`group flex items-start gap-3 rounded-lg p-2.5 cursor-pointer transition-all duration-200 ${
                    isActive
                      ? "bg-cyan-500/15 border-l-4 border-cyan-400 shadow-md shadow-cyan-950/30"
                      : "hover:bg-slate-900/80 border-l-4 border-transparent"
                  }`}
                >
                  <div className="mt-0.5 shrink-0 flex items-center gap-1.5 text-xs font-medium text-cyan-400/90">
                    <User className="h-3.5 w-3.5" />
                    <span className="font-mono bg-slate-900 px-1.5 py-0.5 rounded text-[11px]">
                      {line.speaker}
                    </span>
                  </div>

                  <div className="flex-1 min-w-0">
                    <p className={`text-sm leading-relaxed ${isActive ? "text-cyan-100 font-medium" : "text-slate-300"}`}>
                      {line.text}
                    </p>
                  </div>

                  <span className="text-[10px] font-mono text-slate-500 group-hover:text-cyan-400/70 opacity-0 group-hover:opacity-100 transition-opacity">
                    {formatTime(line.approxStartSeconds)}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
