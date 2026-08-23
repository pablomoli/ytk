import { ArrowClockwise, Play } from "@phosphor-icons/react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useId, useRef, useState } from "react";
import {
  runKnob,
  useAtlas,
  useAtlasFeatures,
  type AtlasCell,
  type AtlasData,
  type FeatureCard,
  type KnobResult,
} from "../api/atlas";
import { ApiError } from "../api/client";
import { HubControls } from "../components/HubControls";
import { Button } from "../components/ui/button";
import {
  SegmentedControl,
  SegmentedControlItem,
} from "../components/ui/segmented-control";
import "../styles.css";

type AtlasSearch = { cell?: string | undefined; latent?: number | undefined };

const validCellKey = (value: unknown): value is string =>
  typeof value === "string" && /^\d+,\d+$/.test(value);

const validLatent = (value: unknown): value is number =>
  typeof value === "number" && Number.isInteger(value) && value >= 0;

export const Route = createFileRoute("/atlas")({
  validateSearch: (search: Record<string, unknown>): AtlasSearch => ({
    cell: validCellKey(search.cell) ? search.cell : undefined,
    latent: validLatent(search.latent) ? search.latent : undefined,
  }),
  component: AtlasPage,
});

// The protagonist thread's tint, section 42 onward. Never the accent.
const CYAN = "#7fd4ff";

function cellKey(cell: AtlasCell) {
  return `${cell.cell[0]},${cell.cell[1]}`;
}

// clipPath ids must be CSS-identifier safe because commas invalidate url(#id).
function clipId(key: string) {
  return `cell-${key.replace(",", "-")}`;
}

function cellLabel(cell: AtlasCell) {
  const stability = cell.stable_05 ? "stable label" : "label unstable across seeds";
  return `Cell ${cell.cell.join(",")}, latent ${cell.label_latent}, ${cell.label ?? "unnamed"}, ${cell.n_scored} notes, ${stability}`;
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
  const width = 100;
  const height = (width * (y1 - y0)) / (x1 - x0);
  const sx = (x: number) => ((x - x0) / (x1 - x0)) * width;
  const sy = (y: number) => ((y1 - y) / (y1 - y0)) * height;
  const maxExcess = Math.max(...atlas.cells.map((cell) => Math.abs(cell.label_excess)), 1e-12);
  const protagonistCell = atlas.protagonist.cell;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="block h-auto w-full">
      {atlas.cells.map((cell) => {
        const key = cellKey(cell);
        const selectedCell = key === selected;
        const protagonist =
          protagonistCell !== null &&
          cell.cell[0] === protagonistCell[0] &&
          cell.cell[1] === protagonistCell[1];
        const strength = Math.abs(cell.label_excess) / maxExcess;
        const x = sx(cell.x0);
        const y = sy(cell.y1);
        const cellWidth = sx(cell.x1) - sx(cell.x0);
        const cellHeight = sy(cell.y0) - sy(cell.y1);
        const choose = () => onSelect(key);

        return (
          <g
            key={key}
            role="button"
            tabIndex={0}
            aria-label={cellLabel(cell)}
            aria-pressed={selectedCell}
            onClick={choose}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                choose();
              }
            }}
            className="group cursor-pointer focus:outline-none"
          >
            <clipPath id={clipId(key)}>
              <rect x={x} y={y} width={cellWidth} height={cellHeight} />
            </clipPath>
            <title>
              #{cell.label_latent} {cell.label ?? ""} · {cell.n_scored} notes
              {cell.stable_05 ? "" : " · label unstable across seeds"}
            </title>
            <rect
              x={x}
              y={y}
              width={cellWidth}
              height={cellHeight}
              fill="var(--accent)"
              fillOpacity={0.08 + 0.3 * strength}
              stroke={selectedCell ? "var(--accent)" : protagonist ? CYAN : "var(--line)"}
              strokeWidth={selectedCell ? 0.5 : 0.25}
              strokeDasharray={protagonist && !selectedCell ? "1.2 0.8" : undefined}
            />
            <rect
              x={x + 0.35}
              y={y + 0.35}
              width={Math.max(cellWidth - 0.7, 0)}
              height={Math.max(cellHeight - 0.7, 0)}
              fill="none"
              stroke="var(--accent)"
              strokeWidth={0.8}
              className="pointer-events-none opacity-0 group-focus-visible:opacity-100"
            />
            <text
              x={(sx(cell.x0) + sx(cell.x1)) / 2}
              y={(sy(cell.y0) + sy(cell.y1)) / 2 - 0.6}
              textAnchor="middle"
              fill="var(--ink)"
              opacity={cell.stable_05 ? 0.95 : 0.45}
              style={{ fontSize: "1.7px" }}
              clipPath={`url(#${clipId(key)})`}
              aria-hidden="true"
            >
              #{cell.label_latent}
            </text>
            <text
              x={(sx(cell.x0) + sx(cell.x1)) / 2}
              y={(sy(cell.y0) + sy(cell.y1)) / 2 + 1.6}
              textAnchor="middle"
              fill="var(--mute)"
              opacity={cell.stable_05 ? 0.9 : 0.45}
              style={{ fontSize: "1.25px" }}
              clipPath={`url(#${clipId(key)})`}
              aria-hidden="true"
            >
              {(cell.label ?? "").slice(0, 22)}
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
      <ul className="flex flex-col gap-1.5">
        {card.exemplars.map((exemplar) => (
          <li key={`${exemplar.source}-${exemplar.title}`} className="flex flex-wrap gap-x-2 text-sm">
            <span className="min-w-0 text-ink">{exemplar.title}</span>
            <span className="font-data text-xs text-mute">
              {exemplar.kind}/{exemplar.source} · {exemplar.act.toFixed(2)}
            </span>
          </li>
        ))}
      </ul>
    );
  }
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      {card.exemplars.map((exemplar) =>
        exemplar.video_id ? (
          <img
            key={`${exemplar.source}-${exemplar.title}`}
            src={`/vault-media/sources/youtube/thumbnails/${exemplar.video_id}-thumb.jpg`}
            alt={exemplar.title}
            className="aspect-video w-full rounded object-cover"
            loading="lazy"
          />
        ) : (
          <div
            key={`${exemplar.source}-${exemplar.title}`}
            role="img"
            aria-label={`${exemplar.title} (${exemplar.source})`}
            className="font-data grid aspect-video w-full place-items-center rounded bg-bg3 text-lg text-mute"
          >
            <span aria-hidden="true">{exemplar.source.slice(0, 1).toUpperCase()}</span>
          </div>
        ),
      )}
    </div>
  );
}

function badgeTone(badge: number) {
  if (badge >= 0.8) return "text-accent";
  if (badge >= 0.5) return "text-ink2";
  return "text-mute";
}

type KnobSnapshot = { query: string; latent: number; clamp: number };
type DisplayResult = { snapshot: KnobSnapshot; value: KnobResult };

function apiDetail(error: ApiError) {
  if (
    typeof error.body === "object" &&
    error.body !== null &&
    "detail" in error.body &&
    typeof error.body.detail === "string"
  ) {
    return error.body.detail;
  }
  return error.message;
}

function knobErrorMessage(error: unknown) {
  if (error instanceof ApiError && error.status === 404) {
    return `Atlas intervention assets are unavailable. ${apiDetail(error)} Then try again.`;
  }
  if (error instanceof Error && /failed to fetch/i.test(error.message)) {
    return "Atlas intervention could not reach the local hub. Check that ytk ui is running, then try again.";
  }
  const detail = error instanceof ApiError ? apiDetail(error) : String(error);
  return `Atlas intervention failed: ${detail}. Check the query and try again.`;
}

function ResultList({
  label,
  rows,
}: {
  label: string;
  rows: KnobResult["base"];
}) {
  return (
    <section className="min-w-0" aria-label={label}>
      <h4 className="mb-2 font-data text-xs uppercase tracking-wide text-mute">{label}</h4>
      <ol className="flex flex-col gap-2">
        {rows.map((row, index) => (
          <li key={`${row.source}-${row.kind}-${row.title}-${index}`} className="min-w-0 text-sm">
            <div className="font-data flex flex-wrap gap-x-2 text-xs text-mute">
              <span>cosine {row.sim.toFixed(2)}</span>
              {row.share === undefined ? null : <span>{Math.round(row.share * 100)}% share</span>}
            </div>
            <div className="overflow-wrap-anywhere text-ink">{row.title}</div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function KnobPanel({ latent, card }: { latent: number; card: FeatureCard | null }) {
  const queryId = useId();
  const clampId = useId();
  const generation = useRef(0);
  const [query, setQuery] = useState("");
  const [clamp, setClamp] = useState(1);
  const [result, setResult] = useState<DisplayResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => {
    generation.current += 1;
    setResult(null);
    setError(null);
    setBusy(false);
  };

  const run = async (requestedClamp: number) => {
    const normalizedQuery = query.trim();
    if (!normalizedQuery) {
      setError("Enter a corpus query before running the intervention.");
      return;
    }

    const snapshot: KnobSnapshot = {
      query: normalizedQuery,
      latent,
      clamp: requestedClamp,
    };
    const requestGeneration = generation.current + 1;
    generation.current = requestGeneration;
    setResult(null);
    setBusy(true);
    setError(null);
    try {
      const value = await runKnob(snapshot.query, snapshot.latent, snapshot.clamp);
      if (generation.current === requestGeneration) setResult({ snapshot, value });
    } catch (caught) {
      if (generation.current === requestGeneration) setError(knobErrorMessage(caught));
    } finally {
      if (generation.current === requestGeneration) setBusy(false);
    }
  };

  const displayed = result?.value;
  const selectedNatural = displayed?.query_latents.find((item) => item.latent === latent);
  const otherQueryLatents = displayed?.query_latents.filter((item) => item.latent !== latent) ?? [];
  const clampedActivation = result ? result.snapshot.clamp * result.value.latent_max : null;

  return (
    <section className="flex min-w-0 flex-col gap-4 rounded-card border border-line bg-bg1 p-4">
      <div>
        <h3 className="font-medium text-ink">Causal intervention</h3>
        <p className="font-data text-xs text-mute">
          #{latent} {card?.name ?? "unnamed latent"}
        </p>
      </div>

      <div className="grid min-w-0 gap-3">
        <label htmlFor={queryId} className="font-data text-sm text-ink2">
          Query
        </label>
        <div className="flex min-w-0 flex-col gap-2 sm:flex-row">
          <input
            id={queryId}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              invalidate();
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") void run(clamp);
            }}
            placeholder="Search your corpus"
            className="min-h-11 min-w-0 flex-1 rounded-lg border border-line bg-bg2 px-3 py-2 text-base text-ink placeholder:text-mute"
          />
          <Button disabled={busy || !query.trim()} onClick={() => void run(clamp)}>
            <Play aria-hidden="true" weight="bold" />
            {busy ? "Running" : "Run intervention"}
          </Button>
        </div>
      </div>

      <div className="grid gap-2">
        <div className="flex items-center justify-between gap-3">
          <label htmlFor={clampId} className="font-data text-sm text-ink2">
            Clamp
          </label>
          <output htmlFor={clampId} className="font-data text-sm tabular-nums text-ink">
            {clamp.toFixed(1)}× max
          </output>
        </div>
        <input
          id={clampId}
          type="range"
          min={0}
          max={2}
          step={0.1}
          value={clamp}
          aria-valuetext={`${clamp.toFixed(1)} times corpus maximum`}
          onChange={(event) => {
            setClamp(Number(event.target.value));
            invalidate();
          }}
          className="min-h-11 w-full cursor-pointer accent-[#e2b04a]"
        />
      </div>

      {error ? (
        <div role="alert" className="rounded-lg border border-line bg-bg2 p-3 text-sm text-ink2">
          <p>{error}</p>
          <Button className="mt-3" variant="outline" onClick={() => void run(clamp)}>
            <ArrowClockwise aria-hidden="true" />
            Try again
          </Button>
        </div>
      ) : null}

      {result && displayed ? (
        <div className="grid min-w-0 gap-4">
          <div className="rounded-lg border border-line bg-bg2 p-3 text-sm text-ink2">
            <p>
              {selectedNatural
                ? `Selected latent naturally active at ${selectedNatural.act.toFixed(2)}.`
                : "Selected latent was not naturally active for this query."} {" "}
              Corpus max {displayed.latent_max.toFixed(2)}; clamped to{" "}
              {clampedActivation?.toFixed(2)}.
            </p>
            {otherQueryLatents.length ? (
              <p className="mt-2 font-data text-xs text-mute">
                Also active: {otherQueryLatents.map((item) => `#${item.latent} at ${item.act.toFixed(2)}`).join(" · ")}
              </p>
            ) : null}
          </div>
          <div className="grid min-w-0 grid-cols-1 gap-4 sm:grid-cols-2">
            <ResultList label="unclamped roundtrip" rows={displayed.base} />
            <ResultList
              label={`clamped ${result.snapshot.clamp.toFixed(1)}×`}
              rows={displayed.clamped}
            />
          </div>
        </div>
      ) : null}
    </section>
  );
}

function AtlasLoadError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const detail = error instanceof ApiError ? apiDetail(error) : String(error);
  return (
    <div role="alert" className="m-4 grid max-w-xl gap-3 rounded-card border border-line bg-bg1 p-5">
      <h1 className="text-xl text-ink">Atlas could not load</h1>
      <p className="text-sm text-ink2">{detail}. Check the Atlas exports, then retry.</p>
      <Button className="justify-self-start" variant="outline" onClick={onRetry}>
        <ArrowClockwise aria-hidden="true" />
        Retry Atlas
      </Button>
    </div>
  );
}

function AtlasPage() {
  const atlas = useAtlas();
  const features = useAtlasFeatures();
  const search = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const [mode, setMode] = useState<"text" | "img">("text");

  if (atlas.isError) {
    return <AtlasLoadError error={atlas.error} onRetry={() => void atlas.refetch()} />;
  }
  if (atlas.isLoading || !atlas.data) {
    return (
      <div role="status" className="grid flex-1 place-items-center text-mute">
        Loading Atlas
      </div>
    );
  }

  const data = atlas.data;
  const cellsByKey = new Map(data.cells.map((cell) => [cellKey(cell), cell]));
  const requestedCell = search.cell ? (cellsByKey.get(search.cell) ?? null) : null;
  const initialCellKey = data.protagonist.cell?.join(",") ?? null;
  const effectiveCellKey = requestedCell ? search.cell ?? null : initialCellKey;
  const selectedCell = effectiveCellKey ? (cellsByKey.get(effectiveCellKey) ?? null) : null;
  const effectiveLatent = requestedCell
    ? (search.latent ?? requestedCell.label_latent)
    : data.protagonist.latent;
  const card = features.data?.cards[String(effectiveLatent)] ?? null;

  const chooseCell = (key: string) => {
    const cell = cellsByKey.get(key);
    if (!cell) return;
    void navigate({ search: { cell: key, latent: cell.label_latent } });
  };

  return (
    <div
      data-testid="atlas-page"
      className="flex min-w-0 flex-1 flex-col overflow-x-hidden overflow-y-auto"
    >
      <HubControls className="justify-between">
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">
          <h1 className="text-xl text-ink">Atlas</h1>
          <span className="font-data text-xs text-mute">
            {data.cells.length} cells · {data.gate.stable_05}/{data.gate.n} stable ·{" "}
            {data.n_joined}/{data.n_map_points} scored
          </span>
        </div>
        <SegmentedControl
          label="Exemplars"
          value={mode}
          onValueChange={(value) => setMode(value as "text" | "img")}
        >
          <SegmentedControlItem value="text">Text</SegmentedControlItem>
          <SegmentedControlItem value="img">Images</SegmentedControlItem>
        </SegmentedControl>
      </HubControls>

      <div className="grid min-w-0 grid-cols-1 gap-4 p-3 md:p-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(22rem,1fr)]">
        <section
          role="group"
          aria-label="Atlas cells"
          className="min-w-0 self-start rounded-card border border-line bg-bg1 p-2 xl:sticky xl:top-4"
        >
          <Lattice atlas={data} selected={effectiveCellKey} onSelect={chooseCell} />
        </section>

        <section
          role="region"
          aria-label="Selected Atlas feature"
          className="flex min-w-0 flex-col gap-3"
        >
          {selectedCell ? (
            <section className="min-w-0 rounded-card border border-line bg-bg1 p-4">
              <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="font-medium text-ink">
                  Cell {selectedCell.cell.join(",")}
                  {selectedCell.theme_label ? ` · ${selectedCell.theme_label}` : ""}
                </h2>
                <span className="font-data text-xs text-mute">
                  {selectedCell.n_scored}/{selectedCell.n_points} scored · head{" "}
                  {Math.round(selectedCell.head_mass * 100)}% · OOD{" "}
                  {Math.round(selectedCell.ood_frac * 100)}%
                </span>
              </div>
              {data.protagonist.cell && effectiveCellKey === data.protagonist.cell.join(",") ? (
                <p className="mb-2 text-xs" style={{ color: CYAN }}>
                  Protagonist estimated cell ({data.protagonist.cell_method})
                </p>
              ) : null}
              <ul className="flex flex-col gap-1">
                {selectedCell.top5.map((latent) => (
                  <li key={latent.latent}>
                    <Button
                      variant="ghost"
                      className={`h-auto w-full min-w-0 justify-start whitespace-normal text-left ${
                        effectiveLatent === latent.latent ? "border-accent text-accent" : "text-ink"
                      }`}
                      aria-pressed={effectiveLatent === latent.latent}
                      onClick={() =>
                        void navigate({
                          search: { cell: effectiveCellKey ?? undefined, latent: latent.latent },
                        })
                      }
                    >
                      <span className="min-w-0">
                        #{latent.latent} {latent.name ?? "unnamed"}
                        <span className="font-data ml-2 text-xs text-mute">
                          excess {latent.excess.toFixed(4)}
                          {latent.outside_null ? "" : " · inside null"}
                        </span>
                      </span>
                    </Button>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {features.isError ? (
            <div role="alert" className="rounded-card border border-line bg-bg1 p-4 text-sm text-ink2">
              <p>Feature details could not load. Check the Atlas feature export and retry.</p>
              <Button className="mt-3" variant="outline" onClick={() => void features.refetch()}>
                <ArrowClockwise aria-hidden="true" />
                Retry details
              </Button>
            </div>
          ) : features.isLoading ? (
            <div role="status" className="rounded-card border border-line bg-bg1 p-4 text-mute">
              Loading feature details
            </div>
          ) : card ? (
            <section className="min-w-0 rounded-card border border-line bg-bg1 p-4">
              <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
                <h2
                  className="font-medium"
                  style={effectiveLatent === data.protagonist.latent ? { color: CYAN } : undefined}
                >
                  #{effectiveLatent} {card.name ?? "unnamed"}
                </h2>
                <span className={`font-data text-xs ${badgeTone(card.badge)}`}>
                  fires {(card.freq * 100).toFixed(1)}% · stability {card.badge.toFixed(2)}
                </span>
              </div>
              <Exemplars card={card} mode={mode} />
            </section>
          ) : null}

          <KnobPanel key={effectiveLatent} latent={effectiveLatent} card={card} />
        </section>
      </div>
    </div>
  );
}
