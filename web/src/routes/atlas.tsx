import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import {
  runKnob,
  useAtlas,
  useAtlasFeatures,
  type AtlasCell,
  type AtlasData,
  type FeatureCard,
  type KnobResult,
} from "../api/atlas";
import { ErrorState } from "../components/StateViews";
import { HubControls } from "../components/HubControls";
import "../styles.css";

export const Route = createFileRoute("/atlas")({ component: AtlasPage });

// The protagonist thread's tint, section 42 onward. Never the accent.
const CYAN = "#7fd4ff";
const BTN = "rounded px-2 py-1 bg-white/5 hover:bg-white/10";

function cellKey(c: AtlasCell) {
  return `${c.cell[0]},${c.cell[1]}`;
}

// clipPath ids must be CSS-identifier safe: a comma in url(#cell-8,9)
// silently disables the clip and labels bleed across cells
function clipId(key: string) {
  return `cell-${key.replace(",", "-")}`;
}

function Lattice({
  atlas,
  selected,
  onSelect,
}: {
  atlas: AtlasData;
  selected: string | null;
  onSelect: (key: string) => void;
}) {
  const xe = atlas.x_edges;
  const ye = atlas.y_edges;
  const [x0, x1] = [xe[0], xe[xe.length - 1]];
  const [y0, y1] = [ye[0], ye[ye.length - 1]];
  const W = 100;
  const H = (W * (y1 - y0)) / (x1 - x0);
  const sx = (x: number) => ((x - x0) / (x1 - x0)) * W;
  // map y up -> svg y down
  const sy = (y: number) => ((y1 - y) / (y1 - y0)) * H;
  const emax = Math.max(...atlas.cells.map((c) => Math.abs(c.label_excess)));
  const pc = atlas.protagonist.cell;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-full w-full">
      {atlas.cells.map((c) => {
        const key = cellKey(c);
        const sel = key === selected;
        const isProt = pc !== null && c.cell[0] === pc[0] && c.cell[1] === pc[1];
        const strength = Math.abs(c.label_excess) / emax;
        return (
          <g key={key} onClick={() => onSelect(key)} className="cursor-pointer">
            <clipPath id={clipId(key)}>
              <rect
                x={sx(c.x0)}
                y={sy(c.y1)}
                width={sx(c.x1) - sx(c.x0)}
                height={sy(c.y0) - sy(c.y1)}
              />
            </clipPath>
            <title>
              #{c.label_latent} {c.label ?? ""} · {c.n_scored} notes
              {c.stable_05 ? "" : " · label unstable across seeds"}
            </title>
            <rect
              x={sx(c.x0)}
              y={sy(c.y1)}
              width={sx(c.x1) - sx(c.x0)}
              height={sy(c.y0) - sy(c.y1)}
              fill="var(--accent)"
              fillOpacity={0.08 + 0.3 * strength}
              stroke={sel ? "var(--accent)" : isProt ? CYAN : "var(--line)"}
              strokeWidth={sel ? 0.5 : 0.25}
              strokeDasharray={isProt && !sel ? "1.2 0.8" : undefined}
            />
            <text
              x={(sx(c.x0) + sx(c.x1)) / 2}
              y={(sy(c.y0) + sy(c.y1)) / 2 - 0.6}
              textAnchor="middle"
              fill="var(--ink)"
              opacity={c.stable_05 ? 0.95 : 0.45}
              style={{ fontSize: "1.7px" }}
              clipPath={`url(#${clipId(key)})`}
            >
              #{c.label_latent}
            </text>
            <text
              x={(sx(c.x0) + sx(c.x1)) / 2}
              y={(sy(c.y0) + sy(c.y1)) / 2 + 1.6}
              textAnchor="middle"
              fill="var(--mute)"
              opacity={c.stable_05 ? 0.9 : 0.45}
              style={{ fontSize: "1.25px" }}
              clipPath={`url(#${clipId(key)})`}
            >
              {(c.label ?? "").slice(0, 22)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function Exemplars({ card, mode }: { card: FeatureCard; mode: "text" | "img" }) {
  if (mode === "text") {
    return (
      <ul className="flex flex-col gap-1">
        {card.exemplars.map((e, i) => (
          <li key={i} className="flex items-baseline gap-2 text-sm">
            <span className="text-ink">{e.title}</span>
            <span className="text-mute font-data text-xs">
              {e.kind}/{e.source} · {e.act.toFixed(2)}
            </span>
          </li>
        ))}
      </ul>
    );
  }
  return (
    <div className="grid grid-cols-3 gap-1.5">
      {card.exemplars.map((e, i) =>
        e.video_id ? (
          <img
            key={i}
            src={`/vault-media/sources/youtube/thumbnails/${e.video_id}-thumb.jpg`}
            alt={e.title}
            title={e.title}
            className="aspect-video w-full rounded object-cover"
            loading="lazy"
          />
        ) : (
          // [T] provenance fallback: the letter says where the note came from
          <div
            key={i}
            title={e.title}
            className="aspect-video w-full rounded bg-bg3 grid place-items-center text-mute font-data text-lg"
          >
            {e.source.slice(0, 1).toUpperCase()}
          </div>
        ),
      )}
    </div>
  );
}

function badgeTone(b: number) {
  if (b >= 0.8) return "text-accent";
  if (b >= 0.5) return "text-ink2";
  return "text-mute";
}

function KnobPanel({ latent, card }: { latent: number; card: FeatureCard | null }) {
  const [query, setQuery] = useState("");
  const [clamp, setClamp] = useState(1.0);
  const [result, setResult] = useState<KnobResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (c: number) => {
    if (!query.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await runKnob(query, latent, c));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-3 rounded-card border border-line bg-bg1 p-4">
      <div className="text-ink font-medium">
        the knob — clamp #{latent} {card?.name ? `“${card.name}”` : ""}
      </div>
      <div className="flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void run(clamp)}
          placeholder="a query for your corpus"
          className="flex-1 rounded border border-line bg-bg2 px-3 py-1.5 text-sm text-ink placeholder:text-mute"
        />
        <button type="button" className={BTN} disabled={busy} onClick={() => void run(clamp)}>
          {busy ? "…" : "run"}
        </button>
      </div>
      <label className="flex items-center gap-3 text-sm text-mute">
        clamp
        <input
          type="range"
          min={0}
          max={2}
          step={0.1}
          value={clamp}
          onChange={(e) => {
            const c = Number(e.target.value);
            setClamp(c);
          }}
          onMouseUp={() => void run(clamp)}
          onTouchEnd={() => void run(clamp)}
          className="flex-1 accent-[#e2b04a]"
        />
        <span className="font-data text-ink w-14 text-right">{clamp.toFixed(1)}x max</span>
      </label>
      <div className="text-xs text-mute">
        section 35's measured range: 0.5x → 30% takeover, 1x → 90%, 2x → single-attractor babble
      </div>
      {error && <div className="text-sm text-mute">{error}</div>}
      {result && (
        <div className="grid grid-cols-2 gap-3">
          {(
            [
              ["base (clamp 0)", result.base],
              [`clamped ${clamp.toFixed(1)}x`, result.clamped],
            ] as const
          ).map(([label, list]) => (
            <div key={label}>
              <div className="mb-1 text-xs uppercase tracking-wide text-mute">{label}</div>
              <ol className="flex flex-col gap-0.5">
                {list.map((r, i) => (
                  <li key={i} className="truncate text-sm text-ink" title={r.title}>
                    <span className="font-data text-mute mr-1">{r.sim.toFixed(2)}</span>
                    {r.title}
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AtlasPage() {
  const atlas = useAtlas();
  const features = useAtlasFeatures();
  const [selCell, setSelCell] = useState<string | null>(null);
  const [selLatent, setSelLatent] = useState<number | null>(null);
  const [mode, setMode] = useState<"text" | "img">("text");

  const cells = atlas.data?.cells ?? [];
  const byKey = useMemo(() => new Map(cells.map((c) => [cellKey(c), c])), [cells]);

  // the page opens on the protagonist's thread
  const effCellKey =
    selCell ??
    (atlas.data?.protagonist.cell ? atlas.data.protagonist.cell.join(",") : null);
  const cell = effCellKey ? (byKey.get(effCellKey) ?? null) : null;
  const effLatent = selLatent ?? atlas.data?.protagonist.latent ?? null;
  const card =
    effLatent !== null ? (features.data?.cards[String(effLatent)] ?? null) : null;

  if (atlas.isError)
    return <ErrorState error={atlas.error} onRetry={() => void atlas.refetch()} />;
  if (atlas.isLoading || !atlas.data)
    return <div className="grid flex-1 place-items-center text-mute">loading the atlas…</div>;

  const a = atlas.data;
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <HubControls>
        <span className="text-sm text-mute">
          {a.cells.length} cells · {a.gate.stable_05}/{a.gate.n} labels survive retraining ·{" "}
          {a.n_joined}/{a.n_map_points} notes scored
        </span>
        <span className="flex-1" />
        {(["text", "img"] as const).map((m) => (
          <button
            key={m}
            type="button"
            className={`${BTN} ${mode === m ? "text-accent" : "text-mute"}`}
            onClick={() => setMode(m)}
          >
            {m.toUpperCase()}
          </button>
        ))}
      </HubControls>
      <div className="grid min-h-0 flex-1 grid-cols-[1.3fr_1fr] gap-4 p-4">
        <div className="min-h-0 rounded-card border border-line bg-bg1 p-2">
          <Lattice atlas={a} selected={effCellKey} onSelect={(k) => setSelCell(k)} />
        </div>
        <div className="flex min-h-0 flex-col gap-3 overflow-y-auto pr-1">
          {cell && (
            <div className="rounded-card border border-line bg-bg1 p-4">
              <div className="mb-1 flex items-baseline justify-between">
                <span className="text-ink font-medium">
                  cell {cell.cell.join(",")}
                  {cell.theme_label ? ` · ${cell.theme_label}` : ""}
                </span>
                <span className="font-data text-xs text-mute">
                  {cell.n_scored}/{cell.n_points} scored · head{" "}
                  {Math.round(cell.head_mass * 100)}% · OOD {Math.round(cell.ood_frac * 100)}%
                </span>
              </div>
              {a.protagonist.cell && effCellKey === a.protagonist.cell.join(",") && (
                <div className="mb-2 text-xs" style={{ color: CYAN }}>
                  the protagonist's estimated cell ({a.protagonist.cell_method})
                </div>
              )}
              <ul className="flex flex-col gap-1">
                {cell.top5.map((t) => (
                  <li key={t.latent}>
                    <button
                      type="button"
                      className={`${BTN} w-full text-left text-sm ${
                        effLatent === t.latent ? "text-accent" : "text-ink"
                      }`}
                      onClick={() => setSelLatent(t.latent)}
                    >
                      #{t.latent} {t.name ?? "(unnamed)"}
                      <span className="font-data ml-2 text-xs text-mute">
                        excess {t.excess.toFixed(4)}
                        {t.outside_null ? "" : " · inside null"}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {card && effLatent !== null && (
            <div className="rounded-card border border-line bg-bg1 p-4">
              <div className="mb-2 flex items-baseline justify-between">
                <span
                  className="font-medium"
                  style={effLatent === a.protagonist.latent ? { color: CYAN } : undefined}
                >
                  #{effLatent} {card.name ?? "(unnamed)"}
                </span>
                <span className={`font-data text-xs ${badgeTone(card.badge)}`}>
                  fires {(card.freq * 100).toFixed(1)}% · seed badge {card.badge.toFixed(2)}
                </span>
              </div>
              <Exemplars card={card} mode={mode} />
              <div className="mt-2 text-xs text-mute">
                names are exemplar-derived hypotheses (section 24); the knob below is the causal
                test
              </div>
            </div>
          )}
          {effLatent !== null && <KnobPanel latent={effLatent} card={card} />}
        </div>
      </div>
    </div>
  );
}
