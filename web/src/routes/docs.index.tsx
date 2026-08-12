import { useEffect, useRef, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import type { DocsSectionSummary } from "../api/docs";
import { useDocsManifest, mediaUrl } from "../api/docs";
import { ErrorState } from "../components/StateViews";
import { mountBackdrop } from "../lib/docsBackdrop";
import "../styles.css";

export const Route = createFileRoute("/docs/")({ component: DocsPage });

const ARROW =
  "absolute top-1/2 z-10 grid h-8 w-8 -translate-y-1/2 place-items-center " +
  "rounded-full bg-black/60 text-lg leading-none text-[var(--ink)] " +
  "opacity-0 transition-opacity duration-150 group-hover:opacity-100 " +
  "focus-visible:opacity-100 hover:bg-black/85";

function DocsCard({ s }: { s: DocsSectionSummary }) {
  const [i, setI] = useState(0);
  const last = s.images.length - 1;
  const show = (e: React.MouseEvent<HTMLButtonElement>, k: number) => {
    // the whole card is a Link; paging must not navigate
    e.preventDefault();
    e.stopPropagation();
    setI(Math.min(Math.max(k, 0), last));
  };
  return (
    <Link
      to="/docs/$section"
      params={{ section: s.id }}
      className="card group block overflow-hidden no-underline !bg-[#101012]"
    >
      <div className="relative">
        {s.images.length ? (
          <img
            src={mediaUrl(s.images[i])}
            alt=""
            loading="lazy"
            className="aspect-[16/10] w-full object-cover object-top opacity-90 transition-opacity duration-200 group-hover:opacity-100"
          />
        ) : (
          <div className="sub grid aspect-[16/10] w-full place-items-center border-b border-white/5">
            no figures
          </div>
        )}
        {i > 0 ? (
          <button
            type="button"
            aria-label="previous figure"
            className={`${ARROW} left-2`}
            onClick={(e) => show(e, i - 1)}
          >
            ‹
          </button>
        ) : null}
        {i < last ? (
          <button
            type="button"
            aria-label="next figure"
            className={`${ARROW} right-2`}
            onClick={(e) => show(e, i + 1)}
          >
            ›
          </button>
        ) : null}
        {s.images.length > 1 ? (
          <div className="absolute inset-x-2 bottom-1 flex gap-1 opacity-0 transition-opacity duration-150 group-hover:opacity-100">
            {s.images.map((im, k) => (
              <button
                key={im}
                type="button"
                aria-label={`show figure ${k + 1}`}
                aria-current={k === i}
                onClick={(e) => show(e, k)}
                className="flex-1 py-1.5"
              >
                <span
                  className={`block h-[3px] rounded-full transition-colors duration-150 ${
                    k === i ? "bg-[var(--accent)]" : "bg-white/25 hover:bg-white/50"
                  }`}
                />
              </button>
            ))}
          </div>
        ) : null}
      </div>
      <div className="p-4">
        <p className="sub text-[var(--mute)]">
          e{s.num.toString().padStart(2, "0")} · {s.images.length}{" "}
          {s.images.length === 1 ? "figure" : "figures"}
          {s.hasVideo ? " · film" : ""}
        </p>
        <h2 className="mt-1 text-lg leading-snug !text-[var(--ink)]">
          {s.title}
        </h2>
        {s.deck ? (
          <p className="mt-1 line-clamp-2 text-sm text-[var(--ink2)]">{s.deck}</p>
        ) : null}
      </div>
    </Link>
  );
}

export function DocsPage() {
  const manifest = useDocsManifest();
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const handle = mountBackdrop(canvas);
    return () => handle.dispose();
  }, []);

  if (manifest.isError)
    return (
      <ErrorState error={manifest.error} onRetry={() => void manifest.refetch()} />
    );

  const data = manifest.data;
  return (
    <div className="relative flex-1 min-h-0 overflow-y-auto bg-black">
      <canvas
        ref={canvasRef}
        aria-hidden
        className="pointer-events-none fixed inset-0 h-full w-full"
      />
      <div className="relative mx-auto max-w-[1400px] px-6 pb-24 pt-14">
        {/* a div, not <header>: theme.css gives header the nav's panel background */}
        <div className="mb-12">
          <p className="sub text-[var(--mute)]">the experiment record</p>
          {/* !: index.css paints h1/h2 unlayered, which beats layered utilities */}
          <h1 className="mt-1 text-3xl !text-[var(--ink)]">
            every question that was actually measured
          </h1>
          {data ? (
            <p className="sub mt-2 text-[var(--mute)]">
              {data.sections.length} sections, newest first · each reproducible
              from a script, none redrawn to agree with later results
            </p>
          ) : null}
        </div>

        {!data ? (
          <p className="sub">loading the record...</p>
        ) : !data.available ? (
          <div className="max-w-[60ch]">
            <h2 className="text-xl !text-[var(--ink)]">the record is not mounted</h2>
            <p className="sub mt-2 normal-case">
              This hub install cannot see docs/assets. Point YTK_REPO_PATH at
              the ytk checkout in ~/.ytk/.env (or the environment) and restart
              the hub.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-x-6 gap-y-10 sm:grid-cols-2 xl:grid-cols-3">
            {data.sections.map((s) => (
              <DocsCard key={s.id} s={s} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
