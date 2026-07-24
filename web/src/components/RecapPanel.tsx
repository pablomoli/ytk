import { Fragment } from "react";
import type { ReactNode } from "react";
import { useRecap } from "../api/recap";
import { renderInline } from "../lib/inlineMarkdown";

/* The recap narrative is small, self-authored markdown. Rather than pull in a
   full markdown dependency, render the handful of block shapes the synthesis
   actually produces (headings, bullets, paragraphs) and reuse renderInline for
   bold/italic. Wikilinks are ytk's own syntax and get their own inline pass. */

const WIKILINK = /\[\[([^\]]+)\]\]/g;

function renderRecapInline(text: string): ReactNode {
  const parts: ReactNode[] = [];
  let last = 0;
  let key = 0;
  let m: RegExpExecArray | null;
  WIKILINK.lastIndex = 0;
  while ((m = WIKILINK.exec(text))) {
    if (m.index > last) {
      parts.push(<Fragment key={key++}>{renderInline(text.slice(last, m.index))}</Fragment>);
    }
    const [target, label] = m[1].split("|");
    parts.push(
      <span key={key++} className="recap-note" title={target}>
        {label ?? target}
      </span>,
    );
    last = m.index + m[0].length;
  }
  if (last < text.length) {
    parts.push(<Fragment key={key++}>{renderInline(text.slice(last))}</Fragment>);
  }
  return parts;
}

function renderMarkdown(md: string): ReactNode[] {
  const blocks: ReactNode[] = [];
  const lines = md.split("\n");
  let para: string[] = [];
  let bullets: string[] = [];
  let key = 0;

  const flushPara = () => {
    if (para.length) {
      blocks.push(<p key={key++}>{renderRecapInline(para.join(" "))}</p>);
      para = [];
    }
  };
  const flushBullets = () => {
    if (bullets.length) {
      blocks.push(
        <ul key={key++}>
          {bullets.map((b, i) => (
            <li key={i}>{renderRecapInline(b)}</li>
          ))}
        </ul>,
      );
      bullets = [];
    }
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      flushBullets();
      flushPara();
      continue;
    }
    const heading = line.match(/^#{1,4}\s+(.*)/);
    const bullet = line.match(/^[-*]\s+(.*)/);
    if (heading) {
      flushBullets();
      flushPara();
      blocks.push(<h3 key={key++}>{renderRecapInline(heading[1])}</h3>);
    } else if (bullet) {
      flushPara();
      bullets.push(bullet[1]);
    } else {
      flushBullets();
      para.push(line);
    }
  }
  flushBullets();
  flushPara();
  return blocks;
}

export function RecapPanel() {
  const recap = useRecap();

  return (
    <div className="recap">
      <div className="recap-actions">
        <button
          className="btn primary"
          onClick={() => recap.mutate(undefined)}
          disabled={recap.isPending}
        >
          {recap.isPending ? "connecting the dots..." : "what's new"}
        </button>
        {recap.data ? (
          <button className="btn ghost" onClick={() => recap.reset()}>
            dismiss
          </button>
        ) : null}
        <span className="recap-hint">
          {recap.isPending
            ? "reading recent ingests + your work"
            : "recap what came in and how it ties to your work"}
        </span>
      </div>
      {recap.isError ? (
        <div className="recap-error" role="alert">
          recap failed: {String(recap.error)}
        </div>
      ) : null}
      {recap.data ? <div className="recap-body">{renderMarkdown(recap.data.markdown)}</div> : null}
    </div>
  );
}
