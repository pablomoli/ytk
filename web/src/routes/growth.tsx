import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useLibrary } from "../api/library";
import { useProfile, type ProfileTheme } from "../api/profile";
import { useGrowthPhilosophy } from "../api/growth";
import { HubControls } from "../components/HubControls";
import {
  DEFAULT_CONSTRAINTS,
  OPERATORS,
  RELIQUARY,
  deriveDNA,
  hashString,
  mutateDNA,
  type Constraints,
  type SeedDNA,
} from "../lib/growth/dna";
import {
  classifyEvent,
  dominantTags,
  joinEvidence,
  tagCountsOf,
  type LibraryItem,
} from "../lib/growth/events";
import { paletteFromCovers } from "../lib/growth/palette";
import { parsePhilosophy } from "../lib/growth/philosophy";
import { mountWorkbench, type WorkbenchHandle, type WorkbenchStatus } from "../lib/growth/scene";
import type { EventInput } from "../lib/growth/scene";
import { pixelateSwap } from "../lib/pixelateSwap";
import "./growth.css";

export const Route = createFileRoute("/growth")({ component: GrowthWorkbench });

type Organism = {
  dna: SeedDNA;
  events: EventInput[];
  evidence: LibraryItem[];
  dominant: string[];
};

const adoptedKey = (id: string) => `growth:adopted:${id}`;
const replayKey = (id: string) => `growth:replay:${id}`;

function loadAdopted(id: string): SeedDNA | null {
  try {
    const raw = localStorage.getItem(adoptedKey(id));
    return raw ? (JSON.parse(raw) as SeedDNA) : null;
  } catch {
    return null;
  }
}

function loadReplay(id: string): number {
  const raw = localStorage.getItem(replayKey(id));
  const n = raw ? Number(raw) : 0;
  return Number.isFinite(n) ? n : 0;
}

function buildOrganism(
  theme: ProfileTheme,
  library: LibraryItem[],
  constraints: Constraints,
  palette: string[] | null,
): Organism {
  // note_ids is the theme's full grounding; older hubs only send the
  // 4-exemplar evidence_ids, which still yields a (short) growth stream.
  const evidence = joinEvidence(theme.note_ids ?? theme.evidence_ids ?? [], library);
  const dominant = dominantTags(evidence);
  const derived = deriveDNA(
    {
      id: theme.id,
      label: theme.label,
      weight: theme.weight,
      n_notes: theme.n_notes,
      fresh_notes: theme.fresh_notes ?? 0,
      tagCounts: tagCountsOf(evidence),
      palette: palette ?? undefined,
    },
    constraints,
  );
  const dna = loadAdopted(theme.id) ?? derived;
  const events = evidence.map((e) => ({
    stem: e.stem,
    title: e.title,
    kind: classifyEvent(e.tags, dominant),
  }));
  return { dna, events, evidence, dominant };
}

function GrowthWorkbench() {
  const profile = useProfile();
  const library = useLibrary(0, undefined, undefined, 900);
  const philosophy = useGrowthPhilosophy();

  const canvas = useRef<HTMLCanvasElement>(null);
  const handle = useRef<WorkbenchHandle>(null);
  const [status, setStatus] = useState<WorkbenchStatus>({
    themeId: null,
    replayed: 0,
    total: 0,
    phase: "resting",
    message: "assembling cultures",
  });
  const [selected, setSelected] = useState<string | null>(null);
  const [palettes, setPalettes] = useState<Record<string, string[]>>({});
  const [thumbs, setThumbs] = useState<Record<string, string>>({});
  const [mutationEpoch, setMutationEpoch] = useState(0);
  const [adoptedTick, setAdoptedTick] = useState(0);
  const [paused, setPaused] = useState(() =>
    new URLSearchParams(window.location.search).has("paused"),
  );
  const [abstraction, setAbstraction] = useState(0);
  const [debugOpen, setDebugOpen] = useState(false);
  const [infoOpen, setInfoOpen] = useState(false);

  const constraints = useMemo(
    () => (philosophy.data ? parsePhilosophy(philosophy.data.text) : DEFAULT_CONSTRAINTS),
    [philosophy.data],
  );

  const libraryItems: LibraryItem[] = useMemo(
    () =>
      (library.data?.items ?? []).map((n) => ({
        stem: n.stem,
        title: n.title,
        url: n.url ?? null,
        tags: n.tags,
        date: n.date ?? null,
        added: n.added,
        thumbnail: n.thumbnail ?? null,
        source: n.source,
      })),
    [library.data],
  );

  const organisms: Map<string, Organism> = useMemo(() => {
    const out = new Map<string, Organism>();
    if (!profile.data) return out;
    for (const theme of profile.data.themes) {
      out.set(
        theme.id,
        buildOrganism(theme, libraryItems, constraints, palettes[theme.id] ?? null),
      );
    }
    out.set(RELIQUARY.themeId, {
      dna: loadAdopted(RELIQUARY.themeId) ?? RELIQUARY,
      events: [],
      evidence: [],
      dominant: [],
    });
    return out;
    // adoptedTick invalidates the memo after an adopt writes localStorage.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile.data, libraryItems, constraints, palettes, adoptedTick]);

  // Extract each theme's palette from its most recent covers, once per theme.
  useEffect(() => {
    let alive = true;
    const run = async () => {
      for (const [id, org] of organisms) {
        if (palettes[id] || id === RELIQUARY.themeId) continue;
        const urls = org.evidence
          .filter((e) => e.url)
          .slice(-3)
          .map((e) => `/api/cover?u=${encodeURIComponent(e.url as string)}`);
        if (!urls.length) continue;
        const palette = await paletteFromCovers(urls);
        if (alive && palette) setPalettes((prev) => ({ ...prev, [id]: palette }));
      }
    };
    void run();
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [organisms]);

  useEffect(() => {
    if (!canvas.current) return;
    handle.current = mountWorkbench(canvas.current, setStatus);
    return () => {
      handle.current?.destroy();
      handle.current = null;
    };
  }, []);

  const persistReplay = useCallback(() => {
    if (!handle.current || !selected) return;
    localStorage.setItem(replayKey(selected), String(handle.current.replayPosition()));
  }, [selected]);

  useEffect(() => {
    const interval = setInterval(persistReplay, 5000);
    return () => {
      clearInterval(interval);
      persistReplay();
    };
  }, [persistReplay]);

  const mutationsFor = useCallback(
    (dna: SeedDNA) => [1, 2, 3, 4].map((s) => mutateDNA(dna, s + mutationEpoch * 4, constraints)),
    [mutationEpoch, constraints],
  );

  const lastLoaded = useRef<{ id: string; events: number; dna: string } | null>(null);

  const select = useCallback(
    (id: string) => {
      if (selected === id) return;
      const selectInner = () => {
        if (selected && handle.current) {
          persistReplay();
          setThumbs((prev) => ({ ...prev, [selected]: handle.current!.snapshot() }));
        }
        lastLoaded.current = null;
        setSelected(id);
      };
      const canvasEl = canvas.current;
      if (canvasEl) pixelateSwap(canvasEl, selectInner);
      else selectInner();
    },
    [selected, persistReplay],
  );

  // Auto-select the heaviest theme once data lands.
  useEffect(() => {
    if (selected || !profile.data || !organisms.size || !handle.current) return;
    const first = profile.data.themes[0]?.id ?? RELIQUARY.themeId;
    select(first);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [organisms, profile.data]);

  // Re-sync the workbench when the selected organism deepens after late data
  // (library page, cover palette) lands — the initial select can race them.
  useEffect(() => {
    if (!selected || !handle.current) return;
    const org = organisms.get(selected);
    if (!org) return;
    const fingerprint = { id: selected, events: org.events.length, dna: JSON.stringify(org.dna) };
    const prev = lastLoaded.current;
    if (
      prev &&
      prev.id === fingerprint.id &&
      prev.events === fingerprint.events &&
      prev.dna === fingerprint.dna
    )
      return;
    lastLoaded.current = fingerprint;
    const resumeFrom =
      prev?.id === selected ? handle.current.replayPosition() : loadReplay(selected);
    handle.current.setOrganism({
      dna: org.dna,
      events: org.events,
      replayFrom: Math.min(resumeFrom, org.events.length),
      constraints,
    });
    handle.current.setMutations(mutationsFor(org.dna));
    if (paused) handle.current.setPaused(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [organisms, selected, constraints, mutationsFor]);

  // Refresh the selected thumb as growth settles.
  useEffect(() => {
    if (!selected || !handle.current) return;
    if (status.phase === "resting" && status.replayed > 0 && status.replayed % 10 === 0) {
      setThumbs((prev) => ({ ...prev, [selected]: handle.current!.snapshot() }));
    }
  }, [status.replayed, status.phase, selected]);

  const current = selected ? organisms.get(selected) : null;
  const mutations = current ? mutationsFor(current.dna) : [];

  const adopt = (i: number) => {
    if (!current || !selected || !handle.current) return;
    const events = current.events;
    const adoptInner = () => {
      const dna = mutations[i];
      localStorage.setItem(adoptedKey(selected), JSON.stringify(dna));
      setAdoptedTick((t) => t + 1);
      handle.current!.setOrganism({
        dna,
        events,
        replayFrom: handle.current!.replayPosition(),
        constraints,
      });
      handle.current!.setMutations(mutationsFor(dna));
    };
    const canvasEl = canvas.current;
    if (canvasEl) pixelateSwap(canvasEl, adoptInner);
    else adoptInner();
  };

  const randomSeed = () => {
    if (!current || !selected || !handle.current) return;
    const dna = mutateDNA(
      current.dna,
      1000 + ((hashString(selected) ^ mutationEpoch) % 8971),
      constraints,
    );
    handle.current.setOrganism({
      dna,
      events: current.events,
      replayFrom: handle.current.replayPosition(),
      constraints,
    });
    handle.current.setMutations(mutationsFor(dna));
    setMutationEpoch((e) => e + 1);
  };

  const loading = profile.isLoading || library.isLoading || philosophy.isLoading;

  return (
    <main className="growth-page">
      <canvas ref={canvas} className="growth-canvas" aria-label="Concept culture petri dish" />

      <HubControls>
        <button
          className="fchip"
          onClick={() => setMutationEpoch((e) => e + 1)}
          disabled={!current}
        >
          new mutation set
        </button>
        <button className="fchip" onClick={randomSeed} disabled={!current}>
          random dna seed
        </button>
        <button
          className={`fchip${paused ? " on" : ""}`}
          onClick={() => {
            const next = !paused;
            setPaused(next);
            handle.current?.setPaused(next);
          }}
        >
          {paused ? "resume" : "pause"}
        </button>
        <button
          className={`fchip${debugOpen ? " on" : ""}`}
          onClick={() => setDebugOpen((d) => !d)}
        >
          debug
        </button>
      </HubControls>

      <nav className="growth-gallery" aria-label="Culture gallery">
        {[...organisms.entries()].map(([id, org]) => (
          <button
            key={id}
            className={`growth-chip${selected === id ? " on" : ""}`}
            onClick={() => select(id)}
            title={org.dna.name}
          >
            {thumbs[id] ? (
              <img src={thumbs[id]} alt="" />
            ) : (
              <span
                className="growth-chip-swatch"
                style={{
                  background: `conic-gradient(${org.dna.palette
                    .map((c, i) => `${c} ${i * 72}deg ${(i + 1) * 72}deg`)
                    .join(", ")})`,
                }}
              />
            )}
          </button>
        ))}
        {loading && <span className="growth-loading">loading cultures...</span>}
      </nav>

      {current && (
        <div className="growth-caption">
          <strong>{current.dna.name}</strong>
          <span>
            {status.replayed}/{status.total} notes · {status.message}
          </span>
          <button className="growth-info-toggle" onClick={() => setInfoOpen((v) => !v)}>
            {infoOpen ? "less" : "info"}
          </button>
        </div>
      )}

      {current && infoOpen && (
        <aside className="growth-panel">
          <div className="growth-swatches">
            {current.dna.palette.map((c, i) => (
              <i key={i} style={{ background: c }} title={c} />
            ))}
          </div>
          <div className="growth-ops">
            {OPERATORS.map((op) => (
              <div key={op} className="growth-op">
                <span>{op.toLowerCase()}</span>
                <div className="growth-op-bar">
                  <i style={{ transform: `scaleX(${current.dna.operators[op]})` }} />
                </div>
              </div>
            ))}
          </div>
          <div className="growth-tags">
            {current.dominant.slice(0, 8).map((t) => (
              <span key={t} className="growth-tag">
                {t}
              </span>
            ))}
          </div>
        </aside>
      )}

      {current && (
        <div className="growth-variants" aria-label="Variant cultures — click to adopt">
          <span className="growth-variants-label">variants · click to adopt</span>
          <div className="growth-variants-row">
            {mutations.map((m, i) => (
              <button
                key={i}
                className="growth-variant-dish"
                onClick={() => adopt(i)}
                title={`M0${i + 1} · density ${m.params.density.toFixed(2)} · motion ${m.params.motion.toFixed(2)}`}
              />
            ))}
          </div>
        </div>
      )}

      {debugOpen && (
        <aside className="growth-debug">
          <button className="fchip" onClick={() => handle.current?.injectDebug("related")}>
            + related
          </button>
          <button className="fchip" onClick={() => handle.current?.injectDebug("novel")}>
            + novel
          </button>
          <button
            className="fchip"
            onClick={() => {
              if (selected) localStorage.removeItem(replayKey(selected));
              handle.current?.reset();
            }}
          >
            reset
          </button>
          <label>
            smooth
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={abstraction}
              onChange={(e) => {
                const v = Number(e.target.value);
                setAbstraction(v);
                handle.current?.setAbstraction(v);
              }}
            />
          </label>
        </aside>
      )}
    </main>
  );
}
