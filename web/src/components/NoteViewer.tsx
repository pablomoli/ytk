import { useEffect, useRef, useState } from "react";
import type { FreshNote } from "../api/fresh";
import { useNote, useSimilarNotes } from "../api/fresh";
import { sourceIcon } from "./icons";
import { parseNote } from "../lib/parseNote";
import type { NoteFrontmatter, NoteSection } from "../lib/parseNote";
import { renderInline } from "../lib/inlineMarkdown";
import { DUR, gsap, reducedMotion } from "../lib/motion";
import { Dialog, DialogContent, DialogTitle } from "./ui/dialog";
import { PixelDissolve } from "./PixelDissolve";

function splitBullets(body: string): string[] {
  return body
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("- "))
    .map((line) => line.slice(2).trim());
}

function splitParagraphs(body: string): string[] {
  return body
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean);
}

function stripTranscriptWrapper(body: string): string {
  return body
    .trim()
    .replace(/^<details>\s*/i, "")
    .replace(/<summary>.*?<\/summary>/is, "")
    .replace(/<\/details>\s*$/i, "")
    .trim();
}

function isYoutubeUrl(url?: string): boolean {
  return Boolean(url && /youtube\.com|youtu\.be/.test(url));
}

function timestampToSeconds(ts: string): number {
  return ts.split(":").reduce((acc, part) => acc * 60 + Number(part), 0);
}

function renderMoment(item: string, frontmatter: NoteFrontmatter) {
  const match = item.match(/^\*\*(\d{1,2}(?::\d{2}){1,2})\*\*\s*(.*)$/);
  if (!match) return renderInline(item);
  const [, timestamp, rest] = match;
  if (frontmatter.url && isYoutubeUrl(frontmatter.url)) {
    const seconds = timestampToSeconds(timestamp);
    const href = `${frontmatter.url}${frontmatter.url.includes("?") ? "&" : "?"}t=${seconds}s`;
    return (
      <>
        <a className="note-ts" href={href} target="_blank" rel="noreferrer">
          {timestamp}
        </a>{" "}
        {renderInline(rest)}
      </>
    );
  }
  return (
    <>
      <strong>{timestamp}</strong> {renderInline(rest)}
    </>
  );
}

function renderSection(section: NoteSection, frontmatter: NoteFrontmatter, key: number) {
  switch (section.kind) {
    case "thesis":
      return (
        <div className="note-callout thesis" key={key}>
          <span className="note-callout-label">thesis</span>
          <p>{renderInline(section.body)}</p>
        </div>
      );
    case "commentary":
      return (
        <div className="note-callout commentary" key={key}>
          <span className="note-callout-label">commentary</span>
          {splitParagraphs(section.body).map((p, i) => (
            <p key={i}>{renderInline(p)}</p>
          ))}
        </div>
      );
    case "insights":
      return (
        <div className="note-callout insights" key={key}>
          <span className="note-callout-label">insights</span>
          <ul>
            {splitBullets(section.body).map((item, i) => (
              <li key={i}>{renderInline(item)}</li>
            ))}
          </ul>
        </div>
      );
    case "concepts":
      return (
        <section className="note-section" key={key}>
          <h3>{section.heading}</h3>
          <ul>
            {splitBullets(section.body).map((item, i) => (
              <li key={i}>{renderInline(item)}</li>
            ))}
          </ul>
        </section>
      );
    case "moments":
      return (
        <section className="note-section" key={key}>
          <h3>{section.heading}</h3>
          <ul>
            {splitBullets(section.body).map((item, i) => (
              <li key={i}>{renderMoment(item, frontmatter)}</li>
            ))}
          </ul>
        </section>
      );
    case "transcript":
      return (
        <details className="note-transcript" key={key}>
          <summary>transcript</summary>
          {splitParagraphs(stripTranscriptWrapper(section.body)).map((p, i) => (
            <p className="note-transcript-line" key={i}>
              {renderInline(p)}
            </p>
          ))}
        </details>
      );
    default: {
      const bullets = splitBullets(section.body);
      return (
        <section className="note-section" key={key}>
          <h3>{section.heading}</h3>
          {bullets.length ? (
            <ul>
              {bullets.map((item, i) => (
                <li key={i}>{renderInline(item)}</li>
              ))}
            </ul>
          ) : (
            splitParagraphs(section.body).map((p, i) => <p key={i}>{renderInline(p)}</p>)
          )}
        </section>
      );
    }
  }
}

/* Structured render of a parsed note: header, tags, callouts, sections, and a
   collapsed transcript so a long one doesn't make the panel infinitely tall.
   Falls back to the raw markdown if parsing finds nothing usable. */
function NoteBody({ raw, note }: { raw: string; note: FreshNote }) {
  const parsed = parseNote(raw);
  const hasContent = parsed.sections.length > 0 || Boolean(parsed.lead);
  if (!hasContent) return <pre>{raw}</pre>;

  const { frontmatter, sections, lead } = parsed;
  const metaParts = [frontmatter.uploader, frontmatter.date, frontmatter.duration].filter(
    Boolean,
  ) as string[];

  return (
    <div className="note-body">
      <div className="note-header">
        <h2 className="note-title">{frontmatter.title || note.title}</h2>
        <div className="note-meta">
          {sourceIcon(note.source)}
          {metaParts.length ? <span>{metaParts.join(" · ")}</span> : null}
          {frontmatter.url ? (
            <a className="card-open" href={frontmatter.url} target="_blank" rel="noreferrer">
              open source
            </a>
          ) : null}
        </div>
      </div>
      {frontmatter.tags.length ? (
        <div className="note-tags">
          {frontmatter.tags.map((tag) => (
            <span key={tag} className="fchip">
              {tag.toLowerCase()}
            </span>
          ))}
        </div>
      ) : null}
      {frontmatter.images.length ? (
        <div className={`note-images${frontmatter.images.length > 1 ? " strip" : ""}`}>
          {frontmatter.images.map((path) => (
            <img
              key={path}
              src={`/vault-media/${path}`}
              loading="lazy"
              alt=""
              onError={(event) => {
                event.currentTarget.style.display = "none";
              }}
            />
          ))}
        </div>
      ) : null}
      {lead ? (
        <div className="note-lead">
          {splitParagraphs(lead).map((p, i) => (
            <p key={i}>{renderInline(p)}</p>
          ))}
        </div>
      ) : null}
      {sections.map((section, i) => renderSection(section, frontmatter, i))}
    </div>
  );
}

/* Radix Dialog supplies the modal behaviors: portal, inert background, focus
   trap and restore, Escape, scroll lock (#136). */
export function NoteViewer({
  note,
  onClose,
  originRect,
}: {
  note: FreshNote;
  onClose: () => void;
  originRect?: DOMRect | undefined;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const content = useNote(note.path);
  const similar = useSimilarNotes(note.path);
  const [revealing, setRevealing] = useState(true);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    gsap.killTweensOf(dialog);
    let tween: ReturnType<typeof gsap.from> | undefined;
    let overlayTween: ReturnType<typeof gsap.from> | undefined;
    let overlayRaf1 = 0, overlayRaf2 = 0;
    if (originRect && !reducedMotion()) {
      const to = dialog.getBoundingClientRect();
      /* transform FLIP: play the panel from the card's rect into place */
      tween = gsap.from(dialog, {
        duration: DUR.morph,
        x: originRect.left + originRect.width / 2 - (to.left + to.width / 2),
        y: originRect.top + originRect.height / 2 - (to.top + to.height / 2),
        scaleX: originRect.width / to.width,
        scaleY: originRect.height / to.height,
        onComplete: () => gsap.set(dialog, { clearProps: "transform" }),
      });
      // the orb's dimmed-sphere backdrop must not vanish in one frame when the
      // apex zoom hands off to this panel; fade the overlay in alongside it.
      // Radix's portal can attach the overlay after this effect runs, so a
      // synchronous query can miss it — try next frame, then once more, then
      // give up silently rather than fight the portal's own timing.
      const tryFadeOverlay = () => {
        const overlay = document.querySelector('[data-slot="dialog-overlay"]');
        if (overlay) overlayTween = gsap.from(overlay, { opacity: 0, duration: DUR.reveal });
        return Boolean(overlay);
      };
      overlayRaf1 = requestAnimationFrame(() => {
        if (!tryFadeOverlay()) overlayRaf2 = requestAnimationFrame(tryFadeOverlay);
      });
    }
    return () => {
      tween?.kill();
      overlayTween?.kill();
      cancelAnimationFrame(overlayRaf1);
      cancelAnimationFrame(overlayRaf2);
      gsap.set(dialog, { clearProps: "transform" });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* Lifecycle cleanup does not report user intent. */
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent
        ref={dialogRef}
        className="h-[calc(100vh-4rem)] w-[min(100vw-4rem,72rem)] p-0"
        aria-describedby={undefined}
      >
        <DialogTitle className="sr-only">{note.title}</DialogTitle>
        <div className="note-panel">
          {revealing ? (
            <PixelDissolve seedKey={note.path} onDone={() => setRevealing(false)} />
          ) : null}
          <button className="btn viewer-close" type="button" onClick={onClose}>
            close
          </button>
          {content.isLoading ? <p>loading note...</p> : null}
          {content.isError ? <p>failed to load note: {String(content.error)}</p> : null}
          {content.data ? <NoteBody raw={content.data.content} note={note} /> : null}
          {similar.data?.length ? (
            <div className="similar-items">
              <span>visually similar</span>
              {similar.data.map((item) => (
                <a
                  key={item.item_id}
                  href={item.url || "#"}
                  target="_blank"
                  rel="noreferrer"
                  title={item.title || item.item_id}
                >
                  <img
                    src={`/api/visual-image?id=${encodeURIComponent(item.item_id)}`}
                    loading="lazy"
                    alt=""
                  />
                </a>
              ))}
            </div>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}
