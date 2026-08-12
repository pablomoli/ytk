import { useEffect, useRef } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useDocsManifest, mediaUrl } from "../api/docs";
import { ErrorState } from "../components/StateViews";
import { mountBackdrop } from "../lib/docsBackdrop";
import "../styles.css";

export const Route = createFileRoute("/docs/")({ component: DocsPage });

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
              <Link
                key={s.id}
                to="/docs/$section"
                params={{ section: s.id }}
                className="card group block overflow-hidden no-underline !bg-[#101012]"
              >
                {s.cover ? (
                  <img
                    src={mediaUrl(s.cover)}
                    alt=""
                    loading="lazy"
                    className="aspect-[16/10] w-full object-cover object-top opacity-90 transition-opacity duration-200 group-hover:opacity-100"
                  />
                ) : (
                  <div className="sub grid aspect-[16/10] w-full place-items-center border-b border-white/5">
                    no figures
                  </div>
                )}
                <div className="p-4">
                  <p className="sub text-[var(--mute)]">
                    e{s.num.toString().padStart(2, "0")} · {s.figures}{" "}
                    {s.figures === 1 ? "figure" : "figures"}
                    {s.hasVideo ? " · film" : ""}
                  </p>
                  <h2 className="mt-1 text-lg leading-snug !text-[var(--ink)]">
                    {s.title}
                  </h2>
                  {s.deck ? (
                    <p className="mt-1 line-clamp-2 text-sm text-[var(--ink2)]">
                      {s.deck}
                    </p>
                  ) : null}
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
