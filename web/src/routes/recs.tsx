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

const MY_LIST = "my list";
const UNSHELVED = "uncategorized";

type Shelf = { name: string; recs: RecCard[] };

/* TMDb's TV genre names and AniList's abbreviations fold into one aisle each,
   so "Sci-Fi & Fantasy" shows don't shelve apart from their movie kin. */
const GENRE_ALIAS: Record<string, string> = {
  "Sci-Fi & Fantasy": "Science Fiction",
  "Sci-Fi": "Science Fiction",
  "Action & Adventure": "Action",
  "War & Politics": "War",
};

/* The specific genre owns the title; broad catch-alls only get what nothing
   else claims. TMDb returns genres in storage order, not relevance order —
   Aliens arrives as [Action, Thriller, Science Fiction] and belongs on the
   science fiction shelf, not action. */
const SHELF_PRIORITY = [
  "Science Fiction",
  "Fantasy",
  "Horror",
  "Western",
  "War",
  "Music",
  "Documentary",
  "History",
  "Animation",
  "Mystery",
  "Crime",
  "Thriller",
  "Romance",
  "Family",
  "Comedy",
  "Adventure",
  "Action",
  "Drama",
];

function primaryShelf(genres: string[] | null): string {
  const normalized = (genres ?? []).map((g) => GENRE_ALIAS[g] ?? g);
  if (normalized.length === 0) return UNSHELVED;
  let best: string | null = null;
  let bestRank = Number.POSITIVE_INFINITY;
  for (const g of normalized) {
    const rank = SHELF_PRIORITY.indexOf(g);
    if (rank !== -1 && rank < bestRank) {
      best = g;
      bestRank = rank;
    }
  }
  // Genres outside the ranking (book shelves like Psychology) keep API order.
  return best ?? normalized[0];
}

/* Blockbuster rule: every title sits on exactly one shelf. Wanted titles are
   pulled up to "my list"; everything else shelves under its primary genre. */
function buildShelves(recs: RecCard[]): Shelf[] {
  const byName = new Map<string, RecCard[]>();
  const myList: RecCard[] = [];
  for (const r of recs) {
    if (r.status === "want") {
      myList.push(r);
      continue;
    }
    const genre = primaryShelf(r.genres);
    const row = byName.get(genre);
    if (row) row.push(r);
    else byName.set(genre, [r]);
  }
  const shelves = [...byName.entries()]
    .map(([name, row]) => ({ name, recs: row }))
    .sort((a, b) => {
      if (a.name === UNSHELVED) return 1;
      if (b.name === UNSHELVED) return -1;
      return b.recs.length - a.recs.length || a.name.localeCompare(b.name);
    });
  for (const shelf of shelves) {
    shelf.recs.sort((a, b) => b.count - a.count || a.title.localeCompare(b.title));
  }
  if (myList.length) {
    myList.sort((a, b) => b.count - a.count || a.title.localeCompare(b.title));
    shelves.unshift({ name: MY_LIST, recs: myList });
  }
  return shelves;
}

function RecsPage() {
  const q = useRecs();
  const setStatus = useSetRecStatus();

  const [tab, setTab] = useState<Tab>("watch");
  const [kind, setKind] = useState<RecKind | null>(null);
  const [showDone, setShowDone] = useState(false);

  // Memoised on q.data so the fallback does not mint a fresh [] every render,
  // which defeated the memos below while the query was loading.
  const recs = useMemo(() => q.data ?? [], [q.data]);

  const counts = useMemo(() => {
    const byKind = new Map<RecKind, number>();
    for (const r of recs) byKind.set(r.kind, (byKind.get(r.kind) ?? 0) + 1);
    const forTab = (t: Tab) => TAB_KINDS[t].reduce((n, k) => n + (byKind.get(k) ?? 0), 0);
    return { byKind, watch: forTab("watch"), read: forTab("read"), total: recs.length };
  }, [recs]);

  const shelves = useMemo(() => {
    const kinds = TAB_KINDS[tab];
    const visible = recs
      .filter((r) => kinds.includes(r.kind))
      .filter((r) => (kind ? r.kind === kind : true))
      .filter((r) => (showDone ? true : r.status !== "seen" && r.status !== "skip"));
    return buildShelves(visible);
  }, [recs, tab, kind, showDone]);

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
    body = <div className="shelf-row">{<Skeletons count={10} />}</div>;
  } else if (q.isError) {
    body = <ErrorState error={q.error} />;
  } else if (shelves.length === 0) {
    body = <EmptyState label="no recommendations yet" />;
  } else {
    body = shelves.map((shelf) => (
      <section key={shelf.name} className="shelf" aria-label={shelf.name}>
        <header className="shelf-head">
          <h2 className={`shelf-name${shelf.name === MY_LIST ? " mine" : ""}`}>{shelf.name}</h2>
          <span className="count">{shelf.recs.length}</span>
        </header>
        <div className="shelf-row">
          {shelf.recs.map((r) => (
            <RecCardView key={r.key} rec={r} onStatus={toggleStatus} />
          ))}
        </div>
      </section>
    ));
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
          <button
            className={`chip${showDone ? " on" : ""}`}
            aria-pressed={showDone}
            onClick={() => setShowDone((v) => !v)}
          >
            seen &amp; skipped
          </button>
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
          in {rec.count} {rec.count === 1 ? "note" : "notes"}
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
