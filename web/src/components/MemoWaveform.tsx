import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent, MouseEvent } from "react";

/* One shared player across all cards; colors read from the theme at draw
   time; canvas sized to its CSS box * devicePixelRatio and redrawn on
   resize. Click seeks (or pauses when already playing this memo). */
const shared: {
  player: HTMLAudioElement | null;
  canvas: HTMLCanvasElement | null;
  peaks: number[];
  decoder: AudioContext | null;
} = { player: null, canvas: null, peaks: [], decoder: null };

const themeColor = (name: string, fallback: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;

function drawWave(canvas: HTMLCanvasElement, peaks: number[], fraction: number) {
  const context = canvas.getContext("2d");
  if (!context || !peaks.length) return;
  const ratio = Math.min(devicePixelRatio || 1, 2);
  const width = Math.max(1, Math.round(canvas.offsetWidth * ratio));
  const height = Math.max(1, Math.round(canvas.offsetHeight * ratio));
  if (canvas.width !== width) canvas.width = width;
  if (canvas.height !== height) canvas.height = height;
  const played = themeColor("--live", "#4ade80");
  const rest = themeColor("--mute", "#83817a");
  const barWidth = width / peaks.length;
  context.clearRect(0, 0, width, height);
  peaks.forEach((peak, index) => {
    context.globalAlpha = index / peaks.length < fraction ? 1 : 0.45;
    context.fillStyle = index / peaks.length < fraction ? played : rest;
    const barHeight = Math.max(4, peak * height * 0.92);
    context.fillRect(
      index * barWidth + barWidth * 0.18,
      (height - barHeight) / 2,
      barWidth * 0.64,
      barHeight,
    );
  });
  context.globalAlpha = 1;
}

async function peaksForAudio(audio: string): Promise<number[]> {
  shared.decoder ??= new window.AudioContext();
  const buffer = await (await fetch(`/api/memo-audio/${encodeURIComponent(audio)}`)).arrayBuffer();
  const decoded = await shared.decoder.decodeAudioData(buffer);
  const data = decoded.getChannelData(0);
  const bars = 56;
  const step = Math.floor(data.length / bars) || 1;
  return Array.from({ length: bars }, (_, index) => {
    let maximum = 0;
    for (let offset = index * step; offset < (index + 1) * step; offset += 32) {
      maximum = Math.max(maximum, Math.abs(data[offset] || 0));
    }
    return maximum;
  });
}

export function MemoWaveform({ audio }: { audio: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const peaksRef = useRef<number[]>([]);
  const [available, setAvailable] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const canvas = canvasRef.current;
    if (!canvas) return;

    void peaksForAudio(audio)
      .then((peaks) => {
        if (cancelled) return;
        peaksRef.current = peaks;
        drawWave(canvas, peaks, 0);
      })
      .catch(() => {
        if (!cancelled) setAvailable(false);
      });

    const ro = new ResizeObserver(() => {
      const playing = shared.canvas === canvas && shared.player && !shared.player.paused;
      const fraction =
        playing && shared.player!.duration
          ? shared.player!.currentTime / shared.player!.duration
          : 0;
      drawWave(canvas, peaksRef.current, fraction);
    });
    ro.observe(canvas);

    return () => {
      cancelled = true;
      ro.disconnect();
      if (shared.canvas === canvas && shared.player) {
        shared.player.pause();
        shared.player = null;
        shared.canvas = null;
        shared.peaks = [];
      }
    };
  }, [audio]);

  if (!available) return null;

  const playAt = (fraction: number, toggle = false) => {
    const canvas = canvasRef.current;
    if (!canvas || !peaksRef.current.length) return;

    if (shared.canvas === canvas && shared.player) {
      if (toggle && !shared.player.paused) {
        shared.player.pause();
        return;
      }
      if (Number.isFinite(shared.player.duration))
        shared.player.currentTime = fraction * shared.player.duration;
      void shared.player.play();
      return;
    }

    if (shared.player && shared.canvas) {
      shared.player.pause();
      drawWave(shared.canvas, shared.peaks, 0);
    }

    const player = new Audio(`/api/memo-audio/${encodeURIComponent(audio)}`);
    shared.player = player;
    shared.canvas = canvas;
    shared.peaks = peaksRef.current;
    player.addEventListener("timeupdate", () =>
      drawWave(canvas, peaksRef.current, player.currentTime / player.duration),
    );
    player.addEventListener("ended", () => {
      drawWave(canvas, peaksRef.current, 0);
      if (shared.player === player) {
        shared.player = null;
        shared.canvas = null;
        shared.peaks = [];
      }
    });
    void player.play();
  };

  const handleClick = (event: MouseEvent<HTMLCanvasElement>) => {
    event.stopPropagation();
    // The canvas is the only control (no separate play/pause button), so a
    // click on the actively-playing waveform must pause it; otherwise it plays
    // from the clicked position.
    playAt(event.nativeEvent.offsetX / event.currentTarget.offsetWidth, true);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLCanvasElement>) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    event.stopPropagation();
    playAt(0, true);
  };

  return (
    <canvas
      ref={canvasRef}
      className="wave"
      tabIndex={0}
      role="button"
      aria-label="Play memo"
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      title="play memo"
    />
  );
}
