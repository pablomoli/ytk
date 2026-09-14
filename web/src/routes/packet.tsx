import { useEffect, useRef, useState } from "react";
import { Outlet, createFileRoute, useNavigate, useParams } from "@tanstack/react-router";
import { useTrack } from "../api/packet";
import { mountPacketTrack } from "../lib/packetTrack";
import { PacketWaves } from "../components/PacketWaves";
import { DEFAULT_LOOK } from "../lib/packetWaves";
import type { WaveLook } from "../lib/packetWaves";
import type { TrackHover, TrackStats } from "../lib/packetTrack";
import { ago, clockText, walkOrder } from "../lib/packetModel";
import "../styles.css";

/* /packet (#213): the track above, the selected packet's page below. The
   selection is the child route's id, so a click, j/k and a link from an ask
   card or `ytk item` all agree. `t` is a replay instant; absent is live. */

export type PacketSearch = { t?: string; lab?: string };

export const Route = createFileRoute("/packet")({
  component: PacketLayout,
  validateSearch: (s: Record<string, unknown>): PacketSearch => ({
    ...(typeof s.t === "string" && s.t ? { t: s.t } : {}),
    ...(typeof s.lab === "string" && s.lab ? { lab: s.lab } : {}),
  }),
});

const RO =
  "absolute font-data text-[12.5px] tracking-[.04em] lowercase text-mute tabular-nums pointer-events-none whitespace-nowrap [text-shadow:0_0_4px_#000]";
const PLATE =
  "relative before:content-[''] before:absolute before:-top-px before:-left-px before:size-3 before:border-t before:border-l before:border-ink2 before:opacity-80 after:content-[''] after:absolute after:-bottom-px after:-right-px after:size-3 after:border-b after:border-r after:border-ink2 after:opacity-80";

function PacketLayout() {
  const { t, lab } = Route.useSearch();
  const [look, setLook] = useState<WaveLook>(DEFAULT_LOOK);
  const params = useParams({ strict: false }) as { id?: string };
  const selected = params.id ? Number(params.id) : null;
  const navigate = useNavigate();
  const track = useTrack(t);
  const stageRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const labelsRef = useRef<HTMLDivElement>(null);
  const mounted = useRef<ReturnType<typeof mountPacketTrack> | undefined>(undefined);
  const [hover, setHover] = useState<TrackHover | null>(null);
  const [stats, setStats] = useState<TrackStats | null>(null);
  const [glError, setGlError] = useState<string | null>(null);
  const [clock, setClock] = useState(() => Date.now());
  const dataRef = useRef(track.data);
  dataRef.current = track.data;

  const goTo = (id: number | null) => {
    if (id == null) void navigate({ to: "/packet", search: (prev) => prev });
    else void navigate({ to: "/packet/$id", params: { id: String(id) }, search: (prev) => prev });
  };
  const goToRef = useRef(goTo);
  goToRef.current = goTo;

  useEffect(() => {
    if (!stageRef.current || !canvasRef.current || !labelsRef.current) return;
    try {
      mounted.current = mountPacketTrack(stageRef.current, canvasRef.current, labelsRef.current, {
        onHover: setHover,
        onSelect: (id) => goToRef.current(id),
        onStats: setStats,
      });
    } catch (err) {
      setGlError(String(err));
      return;
    }
    return () => {
      mounted.current?.dispose();
      mounted.current = undefined;
    };
  }, []);

  useEffect(() => {
    const now = t ? () => Date.parse(t) : () => Date.now();
    mounted.current?.setData(track.data, now);
  }, [track.data, t]);
  useEffect(() => {
    mounted.current?.setSelected(selected);
  }, [selected]);
  useEffect(() => {
    const i = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(i);
  }, []);

  // j and k walk the packets in station order; esc closes the page.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key !== "j" && e.key !== "k" && e.key !== "Escape") return;
      if (e.key === "Escape") {
        goToRef.current(null);
        return;
      }
      const now = t ? Date.parse(t) : Date.now();
      const ids = walkOrder(dataRef.current?.packets ?? [], now);
      if (!ids.length) return;
      const i = ids.indexOf(selected ?? -1);
      const dir = e.key === "j" ? 1 : -1;
      goToRef.current(ids[(i + dir + ids.length) % ids.length]!);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected, t]);

  const instant = t ? Date.parse(t) : clock;

  return (
    <div id="packet-page" className="hub-page">
      <div className="mx-auto box-border flex w-full max-w-[1440px] flex-col gap-3 px-4 pt-3 sm:px-7">
        <div
          ref={stageRef}
          className={`${PLATE} h-[400px] overflow-hidden border border-line bg-[#0b0b0d]`}
          data-testid="track"
        >
          <canvas
            ref={canvasRef}
            className="absolute inset-0 block h-full w-full"
            data-testid="track-canvas"
          />
          <div ref={labelsRef} className="pointer-events-none absolute inset-0" />
          <div className="pointer-events-none absolute top-0 bottom-0 left-1/2 w-px bg-line" />
          <span className={`${RO} top-2.5 left-3.5`}>rose</span>
          <span className={`${RO} top-2.5 left-[calc(50%+14px)]`}>field</span>
          <span className={`${RO} top-2.5 right-3.5`}>
            {clockText(instant)}z{t ? " · replay" : ""}
          </span>
          <span className={`${RO} bottom-2.5 left-3.5`}>
            {track.isError
              ? "track unavailable"
              : stats
                ? `${stats.packets} packets · ${stats.held} held by a model · ${stats.wait} waiting · ${stats.ask} with the owner`
                : track.data
                  ? `${track.data.packets.length} packets`
                  : "loading"}
          </span>
          <span className={`${RO} right-3.5 bottom-2.5 text-accent`}>
            {glError ? "no webgl" : stats ? `${stats.fps} fps` : ""}
          </span>
          {hover ? (
            <div
              className="pointer-events-none absolute z-[5] rounded-md border border-white/15 bg-bg2 px-2.5 py-1.5 text-[13px] whitespace-nowrap"
              style={{ left: hover.x + 14, top: hover.y + 14 }}
              role="tooltip"
            >
              <span className="text-accent tabular-nums">{hover.id}</span> {hover.title}
              <span className="block font-data text-[12.5px] tracking-[.04em] lowercase text-ink2 tabular-nums">
                {hover.station} · {hover.note} · {ago(hover.held)}
              </span>
              <span className="block font-data text-[12.5px] tracking-[.04em] lowercase text-mute tabular-nums">
                {hover.rounds} rounds · {hover.tokens.toLocaleString()} tokens · {hover.calls} of{" "}
                {track.data?.cap ?? 8} calls
              </span>
            </div>
          ) : null}
        </div>
        <div className="relative">
          <PacketWaves
            packets={track.data?.packets}
            t={t}
            look={look}
            className={`${PLATE} h-[260px] overflow-hidden border border-line bg-[#100d0b]`}
          />
          {lab ? <WaveLab look={look} onChange={setLook} /> : null}
        </div>
      </div>
      <Outlet />
      <div className="mx-auto mt-auto box-border flex w-full max-w-[1440px] items-center justify-between gap-6 px-4 pt-4 pb-6 font-data text-[12.5px] tracking-[.04em] text-ink2 lowercase sm:px-7">
        <div className="flex flex-wrap items-center gap-7">
          <span>
            <span className="text-mute">packet</span> <Key>k</Key> <Key>j</Key>
          </span>
          <span>
            <span className="text-mute">answer</span> <Key>1</Key> <Key>2</Key> <Key>3</Key>{" "}
            <Key>4</Key>
          </span>
          <span>
            <Key>esc</Key> <span className="text-mute">close</span>
          </span>
        </div>
        <span className="text-mute">
          {selected != null ? `/packet/${selected}` : "/packet"}
          {t ? `?t=${t}` : ""}
        </span>
      </div>
    </div>
  );
}

/* The color lab (branch only, under ?lab=1): every color idea as a knob,
   so each can be seen alone and in combination before one is chosen. */
function WaveLab({ look, onChange }: { look: WaveLook; onChange: (l: WaveLook) => void }) {
  const range = (key: "ramp" | "temperature" | "hues" | "green", label: string) => (
    <label className="flex items-center gap-2">
      <span className="w-20 text-right">{label}</span>
      <input
        type="range"
        min="0"
        max="1"
        step="0.01"
        value={look[key]}
        className="w-24 accent-accent"
        onChange={(e) => onChange({ ...look, [key]: Number(e.target.value) })}
        aria-label={label}
      />
      <span className="w-8 tabular-nums">{look[key].toFixed(2)}</span>
    </label>
  );
  const flag = (key: "alarm" | "demo", label: string) => (
    <label className="flex items-center gap-2">
      <span className="w-20 text-right">{label}</span>
      <input
        type="checkbox"
        checked={look[key]}
        className="accent-accent"
        onChange={(e) => onChange({ ...look, [key]: e.target.checked })}
        aria-label={label}
      />
    </label>
  );
  return (
    <div className="absolute top-2 right-3 z-10 flex flex-col gap-1 rounded-md border border-line bg-bg1/85 px-3 py-2 font-data text-[11.5px] tracking-[.04em] text-mute lowercase">
      {range("ramp", "phosphor")}
      {range("temperature", "temperature")}
      {range("hues", "station hues")}
      {range("green", "green glow")}
      {flag("alarm", "alarm red")}
      {flag("demo", "demo states")}
    </div>
  );
}

export function Key({ children }: { children: string }) {
  return <span className="rounded border border-line px-[5px] text-xs text-ink2">{children}</span>;
}
