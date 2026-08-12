import { useMemo } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { marked } from "marked";
import { useDocsManifest, useDocsSection, mediaUrl } from "../api/docs";
import { ErrorState } from "../components/StateViews";
import "../styles.css";

export const Route = createFileRoute("/docs/$section")({
  component: DocsSectionPage,
});

/* The README references its figures by bare filename; the hub serves them at
   /docs-media/<section>/<name>. Rewriting here keeps the record's markdown
   untouched on disk. */
function readmeToHtml(md: string, sectionId: string): string {
  const walkTokens = (token: { type: string; href?: string }) => {
    if (token.type === "image" && token.href && !/^([a-z]+:)?\/\//.test(token.href)) {
      token.href = mediaUrl(`${sectionId}/${token.href}`);
    }
  };
  return marked.parse(md, { async: false, gfm: true, walkTokens });
}

/* Block styling rides on the wrapper as arbitrary variants: the record's HTML
   comes out of marked classless, and the CSS ratchet (#136) forbids new
   stylesheet rules. */
const PROSE =
  "text-[15.5px] leading-[1.65] text-[var(--ink)] " +
  "[&_p]:mt-4 [&_a]:text-[var(--accent)] [&_a]:no-underline hover:[&_a]:underline " +
  // !: index.css paints h1/h2/code unlayered (light-scheme palette, 56px h1,
  // inline-flex code) which beats layered utilities; this page decides its own
  "[&_h1]:!text-3xl [&_h1]:!leading-tight [&_h1]:!text-[var(--ink)] " +
  "[&_h2]:!text-[var(--ink)] [&_h3]:!text-[var(--ink)] " +
  "[&_code]:!bg-[#1c1c1f] [&_code]:!text-[var(--ink2)] " +
  "[&_pre_code]:!block [&_pre_code]:!bg-transparent [&_pre_code]:!p-0 " +
  "[&_h2]:mt-12 [&_h2]:text-2xl [&_h3]:mt-8 [&_h3]:text-lg " +
  "[&_img]:mt-8 [&_img]:w-full [&_img]:rounded-[var(--r)] [&_img]:border [&_img]:border-white/10 " +
  "[&_blockquote]:mt-6 [&_blockquote]:border-l-2 [&_blockquote]:border-[var(--accent)] " +
  "[&_blockquote]:pl-4 [&_blockquote]:text-[var(--ink2)] [&_blockquote]:italic " +
  "[&_ul]:mt-4 [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:mt-4 [&_ol]:list-decimal [&_ol]:pl-6 " +
  "[&_li]:mt-1 " +
  "[&_pre]:mt-6 [&_pre]:overflow-x-auto [&_pre]:rounded-[var(--r)] [&_pre]:bg-[#101012] " +
  "[&_pre]:border [&_pre]:border-white/10 [&_pre]:p-4 [&_pre]:normal-case " +
  "[&_code]:normal-case " +
  "[&_table]:mt-6 [&_table]:w-full [&_table]:border-collapse [&_table]:text-sm " +
  "[&_th]:border-b [&_th]:border-white/20 [&_th]:px-2 [&_th]:py-1.5 [&_th]:text-left " +
  "[&_td]:border-b [&_td]:border-white/5 [&_td]:px-2 [&_td]:py-1.5 [&_td]:align-top";

export function DocsSectionPage() {
  const { section } = Route.useParams();
  const detail = useDocsSection(section);
  const manifest = useDocsManifest();

  const html = useMemo(
    () => (detail.data ? readmeToHtml(detail.data.readme, section) : ""),
    [detail.data, section],
  );

  if (detail.isError)
    return <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />;

  const sections = manifest.data?.sections ?? [];
  const at = sections.findIndex((s) => s.id === section);
  // manifest is newest-first; "older" walks forward in the array
  const older = at >= 0 ? sections[at + 1] : undefined;
  const newer = at > 0 ? sections[at - 1] : undefined;
  const videos = detail.data?.files.filter((f) => f.kind === "video") ?? [];

  return (
    <div className="flex-1 min-h-0 overflow-y-auto bg-black">
      <div className="mx-auto max-w-[760px] px-6 pb-24 pt-12">
        <p className="sub">
          <Link to="/docs" className="no-underline text-[var(--accent)]">
            the record
          </Link>{" "}
          · e{section.slice(0, 2)}
        </p>
        {!detail.data ? (
          <p className="sub mt-8">loading the section...</p>
        ) : (
          <>
            {/* biome-ignore lint/security/noDangerouslySetInnerHtml: our own record, rendered locally */}
            <article className={PROSE} dangerouslySetInnerHTML={{ __html: html }} />
            {videos.length ? (
              <div className="mt-10">
                {videos.map((v) => (
                  <video
                    key={v.name}
                    controls
                    preload="metadata"
                    className="mt-4 w-full rounded-[var(--r)] border border-white/10"
                    src={mediaUrl(`${section}/${v.name}`)}
                  />
                ))}
              </div>
            ) : null}
            <nav className="mt-16 flex justify-between border-t border-white/10 pt-6">
              {older ? (
                <Link
                  to="/docs/$section"
                  params={{ section: older.id }}
                  className="sub max-w-[45%] no-underline text-[var(--ink2)] hover:text-[var(--ink)]"
                >
                  ← {older.title}
                </Link>
              ) : (
                <span />
              )}
              {newer ? (
                <Link
                  to="/docs/$section"
                  params={{ section: newer.id }}
                  className="sub max-w-[45%] no-underline text-right text-[var(--ink2)] hover:text-[var(--ink)]"
                >
                  {newer.title} →
                </Link>
              ) : null}
            </nav>
          </>
        )}
      </div>
    </div>
  );
}
