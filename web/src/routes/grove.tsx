// Tree structure, presentation mode, and effect controls persist separately.
import { useEffect, useRef, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { HubControls } from "../components/HubControls";
import { fetchGrovePayload } from "../lib/grove/datatree";
import type { GrovePayload, TopoNode } from "../lib/grove/datatree";
import { DEFAULT_PARAMS } from "../lib/grove/tree";
import type { GroveParams } from "../lib/grove/tree";
import type { GroveHandle } from "../lib/grove/scene";
import type { GroveLook } from "../lib/grove/scene";
import "../styles.css";

const STORAGE = "grove-params-v1";
const DATA_MODE = "grove-data-mode-v1";
const LOOK = "grove-look-v1";

const loadParams = (): GroveParams => {
  try {
    return { ...DEFAULT_PARAMS, ...JSON.parse(localStorage.getItem(STORAGE) ?? "{}") };
  } catch {
    return DEFAULT_PARAMS;
  }
};

const loadLook = (): GroveLook => (localStorage.getItem(LOOK) === "x-ray" ? "x-ray" : "foliage");

type GroveSearch = { readback?: boolean };

export const Route = createFileRoute("/grove")({
  validateSearch: (search: Record<string, unknown>): GroveSearch =>
    search.readback ? { readback: true } : {},
  component: GroveRoute,
});

function GroveRoute() {
  const { readback } = Route.useSearch();
  return readback ? <ReadbackPage /> : <GrovePage />;
}

const KNOBS: Array<{
  key: keyof GroveParams;
  label: string;
  min: number;
  max: number;
  step: number;
}> = [
  { key: "trees", label: "trees", min: 1, max: 5, step: 1 },
  { key: "initialChildren", label: "first limbs", min: 1, max: 4, step: 1 },
  { key: "branchChance", label: "branching", min: 0, max: 0.7, step: 0.05 },
  { key: "stepScale", label: "step", min: 0.25, max: 1.2, step: 0.05 },
  { key: "noise", label: "noise", min: 0, max: 0.6, step: 0.02 },
  { key: "reach", label: "reach", min: 1.5, max: 6, step: 0.1 },
  { key: "upBias", label: "up bias", min: 0, max: 1, step: 0.05 },
  { key: "girth", label: "girth", min: 0.02, max: 0.2, step: 0.01 },
  { key: "girthDecay", label: "taper", min: 0.6, max: 0.97, step: 0.01 },
  { key: "stiffness", label: "stiffness", min: 0, max: 0.95, step: 0.05 },
  { key: "wind", label: "wind", min: 0, max: 1, step: 0.05 },
  { key: "ringSegments", label: "ring verts", min: 4, max: 12, step: 1 },
  { key: "growSeconds", label: "grow time", min: 1, max: 15, step: 0.5 },
  { key: "leafDensity", label: "leaf density", min: 0, max: 120, step: 2 },
  { key: "leafSpread", label: "leaf spread", min: 0.1, max: 0.9, step: 0.02 },
  { key: "leafSize", label: "leaf size", min: 0.5, max: 4, step: 0.1 },
  { key: "paletteTravel", label: "palette travel", min: 0, max: 2, step: 0.05 },
  { key: "paletteMotion", label: "palette motion", min: 0, max: 0.25, step: 0.01 },
  { key: "paletteStrength", label: "palette mix", min: 0, max: 1, step: 0.02 },
  { key: "wireGlow", label: "wire glow", min: 0, max: 2, step: 0.05 },
  { key: "wirePulse", label: "wire pulse", min: 0, max: 1, step: 0.02 },
  { key: "wireBody", label: "wire body", min: 0, max: 1, step: 0.02 },
];

const EFFECT_KEYS = new Set<keyof GroveParams>([
  "paletteTravel",
  "paletteMotion",
  "paletteStrength",
  "wireGlow",
  "wirePulse",
  "wireBody",
]);

function GrovePage() {
  const canvas = useRef<HTMLCanvasElement>(null);
  const handle = useRef<GroveHandle>(undefined);
  const [params, setParams] = useState<GroveParams>(loadParams);
  const [panelOpen, setPanelOpen] = useState(true);
  const [ready, setReady] = useState(false);
  const [payload, setPayload] = useState<GrovePayload | null>(null);
  const [dataMode, setDataMode] = useState(() => localStorage.getItem(DATA_MODE) === "on");
  const [look, setLook] = useState<GroveLook>(loadLook);
  const latestParams = useRef(params);

  useEffect(() => {
    let alive = true;
    // dynamic import keeps three out of every other route's bundle
    void import("../lib/grove/scene").then((mod) => {
      if (!alive || !canvas.current) return;
      handle.current = mod.mountGrove(canvas.current, loadParams(), loadLook());
      setReady(true);
    });
    void fetchGrovePayload().then((p) => {
      if (alive) setPayload(p);
    });
    return () => {
      alive = false;
      handle.current?.destroy();
      handle.current = undefined;
    };
    // mount once; params are pushed through the handle below
  }, []);
  // data mode: structure from bucket topology (/api/grove); aesthetic BFS
  // stays one click away — the calibrated look is never lost, only bypassed
  useEffect(() => {
    if (!ready) return;
    handle.current?.setData(dataMode && payload ? payload : null);
  }, [dataMode, payload, ready]);
  const regenTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const apply = (next: GroveParams, effectsOnly = false) => {
    setParams(next);
    latestParams.current = next;
    localStorage.setItem(STORAGE, JSON.stringify(next));
    if (effectsOnly) {
      handle.current?.setEffects(next);
      return;
    }
    // debounce: slider drags fire per pixel; regenerate once the hand settles
    clearTimeout(regenTimer.current);
    regenTimer.current = setTimeout(() => handle.current?.regenerate(latestParams.current), 160);
  };
  const reseed = () => apply({ ...params, seed: Math.floor(Math.random() * 1e6) });
  const chooseLook = (next: GroveLook) => {
    setLook(next);
    localStorage.setItem(LOOK, next);
    handle.current?.setLook(next);
  };

  return (
    <div className="grove-page">
      <HubControls className="absolute top-3 right-4 z-10 p-0">
        <button className="fchip" onClick={() => handle.current?.replay()}>
          replay growth
        </button>
        <button className="fchip" onClick={reseed}>
          reseed
        </button>
        <button
          className={`fchip${look === "foliage" ? " on" : ""}`}
          onClick={() => chooseLook("foliage")}
        >
          foliage
        </button>
        <button
          className={`fchip${look === "x-ray" ? " on" : ""}`}
          onClick={() => chooseLook("x-ray")}
        >
          x-ray
        </button>
        {payload ? (
          <button
            className={`fchip${dataMode ? " on" : ""}`}
            onClick={() =>
              setDataMode((on) => {
                localStorage.setItem(DATA_MODE, on ? "off" : "on");
                return !on;
              })
            }
          >
            data trees
          </button>
        ) : null}
        <button
          className={`fchip${panelOpen ? " on" : ""}`}
          onClick={() => setPanelOpen((open) => !open)}
        >
          knobs
        </button>
        <span className="count">
          {dataMode && payload ? `${payload.buckets.length} topics` : `seed ${params.seed}`}
        </span>
      </HubControls>
      <canvas ref={canvas} className="grove-canvas" />
      {panelOpen ? (
        <aside className="grove-panel">
          {KNOBS.map(({ key, label, min, max, step }) => (
            <label key={key}>
              <span>{label}</span>
              <input
                type="range"
                min={min}
                max={max}
                step={step}
                value={params[key]}
                onChange={(event) =>
                  apply({ ...params, [key]: Number(event.target.value) }, EFFECT_KEYS.has(key))
                }
              />
              <em>{params[key]}</em>
            </label>
          ))}
        </aside>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// E7 readback (preregistered protocol, docs/grove-lab/e7-preregistration.md).
// The manifest arrives with truth stripped; responses are appended raw and
// correctness is never shown. Inline styles on purpose - trial UI, not product.
// ---------------------------------------------------------------------------

type E7Stimulus = {
  id: string;
  nodes: TopoNode[];
  n_notes: number;
  geometry_seed: number;
  camera_azimuth: number;
};
type E7Trial = {
  trial: string;
  task: string;
  prompt: string;
  bucket: string | null;
  left?: string;
  right?: string;
  top?: string;
  single?: string;
  options?: string[];
};
type E7Manifest = { sha256: string; stimuli: E7Stimulus[]; trials: E7Trial[]; completed: string[] };

const GROW_MS = 900; // growSeconds 0.8 + margin; choices stay hidden until grown

function StimulusCanvas({
  stim,
  height,
  onReady,
}: {
  stim: E7Stimulus;
  height: string;
  onReady: () => void;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    let handle: GroveHandle | undefined;
    let alive = true;
    void import("../lib/grove/scene").then((mod) => {
      if (!alive || !ref.current) return;
      // geometry_seed drives structure realization; camera_azimuth rotates
      // the viewpoint (separated per preregistration amendment 4). Single-
      // bucket payloads render scale-normalized + identically tinted.
      handle = mod.mountGrove(
        ref.current,
        { ...DEFAULT_PARAMS, seed: stim.geometry_seed, growSeconds: 0.8, wind: 0.2 },
        "foliage",
      );
      handle.setData({
        version: 1,
        buckets: [{ bucket: stim.id, n_notes: stim.n_notes, nodes: stim.nodes }],
        azimuth: stim.camera_azimuth,
      });
      onReady(); // scene created + data planted; parent waits GROW_MS on top
    });
    return () => {
      alive = false;
      handle?.destroy();
    };
    // remount per stimulus only; onReady identity is not a remount signal
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stim.id]);
  return (
    <canvas
      ref={ref}
      style={{ width: "100%", height, display: "block", borderRadius: 8, background: "#0a0a0c" }}
    />
  );
}

const chip: React.CSSProperties = {
  padding: "10px 22px",
  borderRadius: 20,
  border: "1px solid #4a4438",
  background: "#1a1a19",
  color: "#e2b04a",
  cursor: "pointer",
  fontSize: 15,
};

function ReadbackPage() {
  const [manifest, setManifest] = useState<E7Manifest | null>(null);
  const [error, setError] = useState("");
  const [index, setIndex] = useState(-1); // resolved after manifest load (resume)
  const [readyCount, setReadyCount] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [choice, setChoice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [failed, setFailed] = useState(false);
  const shownAt = useRef(0);
  const rt = useRef(0);

  useEffect(() => {
    fetch("/api/grove/e7")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then((m: E7Manifest) => {
        setManifest(m);
        // resume: first trial the server has no response for
        const done = new Set(m.completed);
        const next = m.trials.findIndex((t) => !done.has(t.trial));
        setIndex(next === -1 ? m.trials.length : next);
      })
      .catch(() => setError("no manifest - run scripts.grove_lab.e7_manifest first"));
  }, []);
  // per-trial reset: nothing is clickable and RT does not run until every
  // canvas reports ready AND the growth animation has finished (H4)
  useEffect(() => {
    setReadyCount(0);
    setRevealed(false);
    setChoice(null);
    setFailed(false);
  }, [index]);

  const trial =
    manifest && index >= 0 && index < manifest.trials.length ? manifest.trials[index] : null;
  const canvasCount = trial ? (trial.single ? 1 : trial.top ? 3 : 2) : 0;
  useEffect(() => {
    if (!trial || readyCount < canvasCount) return;
    const t = setTimeout(() => {
      setRevealed(true);
      shownAt.current = performance.now();
    }, GROW_MS);
    return () => clearTimeout(t);
  }, [readyCount, canvasCount, trial]);

  if (error) return <div style={{ padding: 40, color: "#c3c2b7" }}>{error}</div>;
  if (!manifest || index < 0)
    return <div style={{ padding: 40, color: "#c3c2b7" }}>loading manifest...</div>;
  if (!trial) {
    return (
      <div style={{ padding: 40, color: "#c3c2b7", fontSize: 18 }}>
        done - all {manifest.trials.length} trials logged. thank you, subject.
      </div>
    );
  }

  const stim = (id?: string) => manifest.stimuli.find((s) => s.id === id)!;
  const onReady = () => setReadyCount((c) => c + 1);
  const pick = (c: string) => {
    if (!revealed || submitting) return;
    rt.current = Math.round(performance.now() - shownAt.current);
    setChoice(c);
  };
  const submit = (confidence: number) => {
    if (submitting || choice === null) return;
    setSubmitting(true);
    setFailed(false);
    fetch("/api/grove/e7/response", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ trial: trial.trial, choice, confidence, rt_ms: rt.current }),
    })
      .then((r) => {
        // ok or already-answered (duplicate/conflict): the trial is recorded
        if (r.ok || r.status === 409) {
          setSubmitting(false);
          setIndex((i) => i + 1);
        } else throw new Error(`${r.status}`);
      })
      .catch(() => {
        setSubmitting(false);
        setFailed(true);
      });
  };
  const isPair = !trial.single;
  const twoHigh = trial.top ? "34vh" : "56vh";

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#0a0a0c",
        padding: "18px 26px",
        fontFamily: "inherit",
      }}
    >
      <div style={{ color: "#52514e", fontSize: 13, marginBottom: 4 }}>
        trial {index + 1} / {manifest.trials.length}
        {trial.task === "practice" ? " - practice (not scored)" : ""}
      </div>
      <div style={{ color: "#e2b04a", fontSize: 24, marginBottom: 14 }}>{trial.prompt}</div>
      {trial.top ? (
        <div style={{ marginBottom: 10 }}>
          <div style={{ color: "#52514e", fontSize: 12, marginBottom: 4 }}>anchor</div>
          <StimulusCanvas stim={stim(trial.top)} height="30vh" onReady={onReady} />
        </div>
      ) : null}
      {isPair ? (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          {(["left", "right"] as const).map((side) => (
            <div key={`${trial.trial}-${side}`}>
              <StimulusCanvas stim={stim(trial[side])} height={twoHigh} onReady={onReady} />
              {revealed && choice === null ? (
                <button
                  style={{ ...chip, marginTop: 10, width: "100%" }}
                  onClick={() => pick(side)}
                >
                  {side}
                </button>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <div>
          <StimulusCanvas stim={stim(trial.single)} height="52vh" onReady={onReady} />
          {revealed && choice === null ? (
            <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
              {trial.options?.map((o) => (
                <button key={o} style={chip} onClick={() => pick(o)}>
                  {o}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      )}
      {!revealed ? <div style={{ marginTop: 16, color: "#52514e" }}>growing...</div> : null}
      {choice !== null && !failed ? (
        <div style={{ marginTop: 16 }}>
          <span style={{ color: "#c3c2b7", marginRight: 12 }}>confidence:</span>
          {[1, 2, 3, 4, 5].map((c) => (
            <button
              key={c}
              disabled={submitting}
              style={{ ...chip, marginRight: 8, opacity: submitting ? 0.4 : 1 }}
              onClick={() => submit(c)}
            >
              {c}
            </button>
          ))}
        </div>
      ) : null}
      {failed ? (
        <div style={{ marginTop: 16, color: "#e66767" }}>
          response not saved -{" "}
          <button style={chip} onClick={() => setFailed(false)}>
            retry confidence
          </button>
        </div>
      ) : null}
    </div>
  );
}
