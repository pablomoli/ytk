import type { TrackPacket } from "../api/packet";
import { MODEL_STATIONS, STATIONS, heldFor, logp } from "./packetModel";

/* The waves (#213): one channel per station, an oscilloscope trace in warm
   phosphor. Every channel peaks at the same height; activity is frequency
   and richness, never height. A model at work turns its channel green.
   Values are the owner's, read off the spike's knobs on 2026-09-13; constants. */

const FREQ = 2.8;
const MOTION = 1.2;
const HARMONICS = 0.13;
const BREATH = 1.67;
const IDLE = 0.86;
const PERSIST = 0.83;
const OFFSET = 0.69;

const N = STATIONS.length;
const BG = "#100d0b";
const IDLE_COL = "#6f665a";
const BRASS = "#e2b04a";
const LIVE = "#4ade80";

function nhash(x: number, y: number) {
  const h = Math.sin(x * 127.1 + y * 311.7) * 43758.5453;
  return h - Math.floor(h);
}
function vnoise(x: number, y: number) {
  const xi = Math.floor(x),
    yi = Math.floor(y),
    xf = x - xi,
    yf = y - yi;
  const u = xf * xf * (3 - 2 * xf),
    v = yf * yf * (3 - 2 * yf);
  const a = nhash(xi, yi),
    b = nhash(xi + 1, yi),
    c = nhash(xi, yi + 1),
    d = nhash(xi + 1, yi + 1);
  return (a + (b - a) * u + (c + (d - c) * u - (a + (b - a) * u)) * v) * 2 - 1;
}
const fbm = (x: number, y: number) =>
  vnoise(x, y) * 0.55 +
  vnoise(x * 2.1 + 7.3, y * 2.1 - 3.1) * 0.3 +
  vnoise(x * 4.3 - 2.2, y * 4.3 + 9.7) * 0.15;

/* The look, locked by the owner on the lab (2026-09-13) with every option
   in view: the phosphor ramp at 0.57, station hues at 1, the model glow at
   1, no alarm red. Temperature was tried and dropped: under the hue tint
   it could not be seen. */
const RAMP = 0.57;
const HUES = 1;
const GREEN = 1;

const AFTERGLOW = "#7a2a14";
const CORE = "#fff4d6";
const STATION_HUES = ["#9085e9", "#d95926", "#199e70", "#c98500", "#d55181", "#3987e5", "#e66767"];

function hex(h: string): [number, number, number] {
  return [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
}
function mixRgb(a: string, b: string, t: number): string {
  // a may already be an rgb() string from a previous mix
  const parse = (s: string): [number, number, number] =>
    s.startsWith("#")
      ? hex(s)
      : (s.match(/\d+/g)!.slice(0, 3).map(Number) as [number, number, number]);
  const A = parse(a),
    B = parse(b);
  const c = A.map((v, i) => Math.round(v + (B[i]! - v) * Math.min(1, Math.max(0, t))));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

export type PacketWaves = {
  setData(packets: TrackPacket[] | undefined, nowMs: () => number): void;
  dispose(): void;
};

export function mountPacketWaves(host: HTMLElement, canvas: HTMLCanvasElement): PacketWaves {
  const cx = canvas.getContext("2d");
  if (!cx) throw new Error("2d canvas is unavailable");
  let packets: TrackPacket[] = [];
  let nowMs: () => number = () => Date.now();
  let W = 0,
    H = 0,
    T = 0,
    last = performance.now(),
    raf = 0;
  const load = new Float32Array(N),
    live = new Float32Array(N),
    cnt = new Int32Array(N);
  const sm = new Float32Array(N),
    smL = new Float32Array(N);

  const measure = () => {
    load.fill(0);
    live.fill(0);
    cnt.fill(0);
    const t = nowMs();
    for (const p of packets) {
      const i = STATIONS.indexOf(p.station.name as (typeof STATIONS)[number]);
      if (i < 0) continue;
      cnt[i]!++;
      load[i]! += logp(heldFor(p.station, t));
      if (p.station.model) live[i] = 1;
    }
  };

  const frame = (now: number) => {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    T += dt * MOTION;
    const r = host.getBoundingClientRect();
    const px = Math.min(2, devicePixelRatio || 1);
    if (r.width !== W || r.height !== H) {
      W = r.width;
      H = r.height;
      canvas.width = W * px;
      canvas.height = H * px;
      cx.setTransform(px, 0, 0, px, 0, 0);
      cx.fillStyle = BG;
      cx.fillRect(0, 0, W, H);
    }
    cx.setTransform(px, 0, 0, px, 0, 0);
    // phosphor: the last frame decays instead of vanishing
    cx.fillStyle = `rgba(16,13,11,${1 - PERSIST * 0.82})`;
    cx.fillRect(0, 0, W, H);
    measure();
    const e = 1 - Math.pow(0.02, dt);
    for (let i = 0; i < N; i++) {
      sm[i]! += (load[i]! - sm[i]!) * e;
      smL[i]! += (live[i]! - smL[i]!) * e;
    }
    const left = 92,
      right = W - 14,
      span = right - left;
    // channels: a wave never leaves its own row
    const pad = H * 0.09,
      rowH = (H - 2 * pad) / N,
      amp = rowH * 0.44;
    // the ruler: fine ticks along the bottom edge, a long one every fifth
    cx.strokeStyle = "rgba(240,238,231,0.22)";
    cx.lineWidth = 1;
    cx.beginPath();
    for (let d = 0; d <= 100; d++) {
      const x = left + (span * d) / 100;
      const h = d % 10 === 0 ? 7 : d % 5 === 0 ? 4 : 2;
      cx.moveTo(x, H - 1);
      cx.lineTo(x, H - 1 - h);
    }
    cx.stroke();
    for (let i = 0; i < N; i++) {
      const cy = pad + rowH * (i + 0.5),
        c = cnt[i]!,
        L = sm[i]!,
        lv = smL[i]!;
      const Ls = L / (L + 1.2),
        act = Math.min(1, L * 3);
      // idle channels already carry a few cycles; load and a live model add more
      const f = FREQ * (2.4 + 2.6 * Ls + lv * 1.2);
      const w = (1.5 + i * 0.13) * (1 + 1.8 * Ls + lv * 1.4);
      const h2 = HARMONICS * (0.15 + 0.85 * Ls);
      const A = amp * (IDLE + (1 - IDLE) * act);
      // the color: brass for a packet, tinted toward the station's hue, green for a model at work
      let col: string = c ? BRASS : IDLE_COL;
      col = mixRgb(col, STATION_HUES[i]!, HUES * (c ? 0.85 : 0.5));
      if (lv > 0.5) col = mixRgb(col, LIVE, Math.min(1, 0.6 + GREEN * 0.4));
      // each channel is offset along x: a golden-ratio stagger plus a slow drift of its own
      const xo = ((i * 0.618034) % 1) + fbm(T * 0.07 + i * 3.3, i * 0.7) * 0.35 * OFFSET;
      cx.beginPath();
      for (let s = 0; s <= span; s += 1.5) {
        const x = s / span + xo * OFFSET;
        const ph = x * Math.PI * 2 * f - T * w + i * 1.3;
        const y1 = Math.sin(ph);
        const y2 = Math.sin(ph * 2.01 + T * 0.7 + i) * h2;
        const y3 = Math.sin(ph * 3.02 - T * 0.4) * h2 * 0.4;
        const env =
          0.72 + 0.28 * Math.sin(x * Math.PI * 2 * 0.6 - T * 0.35 + i * 0.9) * (0.4 + 0.6 * BREATH);
        const n =
          fbm(x * (2.5 + Ls * 5) + T * 0.45 + i * 13, T * 0.25 + i * 5) *
          BREATH *
          (0.06 + Ls * 0.35) *
          (1 + lv * 0.7 * Math.sin(T * 5));
        const y = cy - A * (((y1 + y2 + y3) / (1 + h2 * 1.4)) * env + n);
        if (s === 0) cx.moveTo(left, y);
        else cx.lineTo(left + s, y);
      }
      const glow = c ? (lv > 0.5 ? 12 + GREEN * 10 : 12) : 5;
      if (RAMP > 0) {
        // afterglow first: a wide, cool stroke the persistence keeps
        cx.shadowBlur = 0;
        cx.strokeStyle = mixRgb(col, AFTERGLOW, 0.75);
        cx.globalAlpha = (c ? 0.35 : 0.18) * RAMP;
        cx.lineWidth = c ? 7 : 4;
        cx.stroke();
      }
      cx.shadowColor = col;
      cx.shadowBlur = glow;
      cx.strokeStyle = col;
      cx.globalAlpha = c ? 0.95 : 0.5;
      cx.lineWidth = c ? 1.3 : 1;
      cx.stroke();
      if (RAMP > 0 && c) {
        // the core: thin and near white
        cx.shadowBlur = 0;
        cx.strokeStyle = mixRgb(col, CORE, 0.7 * RAMP);
        cx.globalAlpha = 0.9 * RAMP;
        cx.lineWidth = 0.6;
        cx.stroke();
      }
      cx.shadowBlur = 0;
      cx.globalAlpha = 1;
      // a three-tick scale where the trace enters the row: +1, 0, -1
      cx.strokeStyle = "rgba(240,238,231,0.22)";
      cx.lineWidth = 1;
      cx.beginPath();
      for (const k of [-1, 0, 1]) {
        const y = Math.round(cy + k * amp) + 0.5;
        cx.moveTo(left - 6, y);
        cx.lineTo(left - (k === 0 ? 1 : 3), y);
      }
      cx.moveTo(left - 6.5, cy - amp);
      cx.lineTo(left - 6.5, cy + amp);
      cx.stroke();
      cx.font = "11.5px Newsreader, Georgia, serif";
      cx.textAlign = "right";
      cx.fillStyle = col;
      cx.globalAlpha = c ? 1 : 0.55;
      cx.fillText(STATIONS[i]! + (c ? `  ${c}` : ""), left - 14, cy + 4);
      cx.globalAlpha = 1;
    }
    raf = requestAnimationFrame(frame);
  };
  raf = requestAnimationFrame(frame);
  return {
    setData(next, clock) {
      packets = next ?? [];
      nowMs = clock;
    },
    dispose() {
      cancelAnimationFrame(raf);
    },
  };
}

export const WAVE_MODEL_STATIONS = MODEL_STATIONS;
