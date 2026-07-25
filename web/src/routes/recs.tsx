import { useMemo, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useRecs, useSetRecStatus } from "../api/recs";
import type { RecCard, RecKind, RecStatus } from "../api/recs";
import { HubControls } from "../components/HubControls";
import { Skeletons } from "../components/Skeletons";
import { EmptyState, ErrorState } from "../components/StateViews";
import "../styles.css";

export const Route = createFileRoute("/recs")({
  component: RecsPage,
});

type Tab = "watch" | "read";

const TAB_KINDS: Record<Tab, RecKind[]> = {
  watch: ["movie", "show", "anime"],
  read: ["book", "manga"],
};

const STATUSES: Exclude<RecStatus, null>[] = ["want", "seen", "skip"];

function RecsPage() {
  const q = useRecs();
  const setStatus = useSetRecStatus();

  const [tab, setTab] = useState<Tab>("watch");
  const [kind, setKind] = useState<RecKind | null>(null);

  // Memoised on q.data so the fallback does not mint a fresh [] every render,
  // which defeated the two memos below while the query was loading.
  const recs = useMemo(() => q.data ?? [], [q.data]);

  const counts = useMemo(() => {
    const byKind = new Map<RecKind, number>();
    for (const r of recs) byKind.set(r.kind, (byKind.get(r.kind) ?? 0) + 1);
    const forTab = (t: Tab) => TAB_KINDS[t].reduce((n, k) => n + (byKind.get(k) ?? 0), 0);
    return { byKind, watch: forTab("watch"), read: forTab("read"), total: recs.length };
  }, [recs]);

  const visible = useMemo(() => {
    const kinds = TAB_KINDS[tab];
    return recs
      .filter((r) => kinds.includes(r.kind))
      .filter((r) => (kind ? r.kind === kind : true))
      .sort((a, b) => b.count - a.count);
  }, [recs, tab, kind]);

  const selectTab = (t: Tab) => {
    setTab(t);
    setKind(null);
  };

  const toggleKind = (k: RecKind) => setKind((cur) => (cur === k ? null : k));

  const toggleStatus = (r: RecCard, target: Exclude<RecStatus, null>) => {
    const status: RecStatus = r.status === target ? null : target;
    setStatus.mutate({ key: r.key, status });
  };

  let body;
  if (q.isLoading) {
    body = <div className="rec-grid">{<Skeletons count={10} />}</div>;
  } else if (q.isError) {
    body = <ErrorState error={q.error} />;
  } else if (visible.length === 0) {
    body = <EmptyState label="no recommendations yet" />;
  } else {
    body = (
      <div className="rec-grid">
        {visible.map((r) => (
          <RecCardView key={r.key} rec={r} onStatus={toggleStatus} />
        ))}
      </div>
    );
  }

  return (
    <div id="recs-page" className="hub-page">
      <HubControls>
        <span className="count">
          {counts.total} recs · {counts.watch} watch · {counts.read} read
        </span>
      </HubControls>
      <div className="hub-body recs">
        <div className="rec-tabs" role="tablist" aria-label="Recommendation groups">
          {(["watch", "read"] as Tab[]).map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              className={`rec-tab${tab === t ? " on" : ""}`}
              onClick={() => selectTab(t)}
            >
              {t} <span className="count">{t === "watch" ? counts.watch : counts.read}</span>
            </button>
          ))}
        </div>
        <div className="chips rec-kinds">
          {TAB_KINDS[tab].map((k) => (
            <button
              key={k}
              className={`chip${kind === k ? " on" : ""}`}
              aria-pressed={kind === k}
              onClick={() => toggleKind(k)}
            >
              {k} <span className="count">{counts.byKind.get(k) ?? 0}</span>
            </button>
          ))}
        </div>
        {body}
      </div>
    </div>
  );
}

function RecCardView({
  rec,
  onStatus,
}: {
  rec: RecCard;
  onStatus: (r: RecCard, target: Exclude<RecStatus, null>) => void;
}) {
  const [open, setOpen] = useState(false);
  const [broken, setBroken] = useState(false);
  const showPoster = rec.poster && !broken;

  return (
    <article className={`rec-card${rec.status ? ` ${rec.status}` : ""}`}>
      <div className="rec-poster">
        {showPoster ? (
          <img
            src={rec.poster ?? undefined}
            alt=""
            loading="lazy"
            onError={() => setBroken(true)}
          />
        ) : (
          <div className="rec-poster-fallback">
            <span className="rec-poster-title">{rec.title}</span>
            <span className="rec-poster-kind">{rec.kind}</span>
          </div>
        )}
        {rec.rating != null ? (
          <span className="rec-rating" title={`rating ${rec.rating}`}>
            {rec.rating.toFixed(1)}
          </span>
        ) : null}
      </div>
      <div className="rec-body">
        <h3 className="rec-title title" title={rec.title}>
          {rec.title}
        </h3>
        <div className="rec-meta">
          {rec.year != null ? <span className="rec-year">{rec.year}</span> : null}
          {rec.creator ? <span className="rec-creator">{rec.creator}</span> : null}
        </div>
        <button className="rec-count" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          recommended in {rec.count} {rec.count === 1 ? "note" : "notes"}
        </button>
        {open ? (
          <ul className="rec-sources">
            {rec.sources.map((s, i) => (
              <li key={`${s.path}-${i}`} className="rec-source">
                <span className="rec-source-title">{s.title}</span>
                <span className="rec-source-path">{s.path}</span>
              </li>
            ))}
          </ul>
        ) : null}
        <div className="rec-actions">
          {STATUSES.map((s) => (
            <button
              key={s}
              className={`btn tiny${rec.status === s ? " on" : ""}`}
              aria-pressed={rec.status === s}
              onClick={() => onStatus(rec, s)}
            >
              {s}
            </button>
          ))}
        </div>
      </div>
    </article>
  );
}
