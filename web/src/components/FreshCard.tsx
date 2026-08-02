import { useRef, useState } from "react";
import type { FormEvent, MouseEvent } from "react";
import { ApiError, apiSend } from "../api/client";
import type { FreshNote } from "../api/fresh";
import { copyAskPrompt } from "../lib/askPrompt";
import { useHoverDecode } from "../lib/useHoverDecode";
import { sourceIcon } from "./icons";
import { MemoWaveform } from "./MemoWaveform";
import { PixelBloom } from "./PixelBloom";
import { PixelDissolve } from "./PixelDissolve";

const REFLECT_QUESTION = "why did you save this?";

type ReflectState = "idle" | "sending" | "reflecting" | "busy";

export function FreshCard({
  note,
  onOpen,
  onDelete,
}: {
  note: FreshNote;
  onOpen: (note: FreshNote, rect?: DOMRect) => void;
  onDelete: (note: FreshNote) => void;
}) {
  const [imageFailed, setImageFailed] = useState(false);
  const [askCopied, setAskCopied] = useState(false);
  const [revealed, setRevealed] = useState(false); // image bytes arrived
  const [reveal, setReveal] = useState(true); // dissolve still owed
  const [reflectOpen, setReflectOpen] = useState(false);
  const [reflectAnswer, setReflectAnswer] = useState("");
  const [reflectState, setReflectState] = useState<ReflectState>("idle");
  const isMemo = note.source === "memo";
  const cardRef = useRef<HTMLElement>(null);
  const decode = useHoverDecode();

  const open = () => onOpen(note, cardRef.current?.getBoundingClientRect());
  const ask = async () => {
    if (!(await copyAskPrompt(note.path))) return;
    setAskCopied(true);
    window.setTimeout(() => setAskCopied(false), 1500);
  };
  const toggleReflect = () => {
    setReflectOpen((openNow) => !openNow);
    if (reflectState === "busy") setReflectState("idle");
  };
  const submitReflection = (event: FormEvent) => {
    event.preventDefault();
    const answer = reflectAnswer.trim();
    if (!answer || reflectState === "sending") return;
    setReflectState("sending");
    apiSend<{ status: string }>("/api/reflect", "POST", {
      path: note.path,
      question: REFLECT_QUESTION,
      answer,
    })
      .then(() => {
        setReflectState("reflecting");
        setReflectOpen(false);
        setReflectAnswer("");
        window.setTimeout(() => setReflectState("idle"), 2000);
      })
      .catch((error: unknown) => {
        setReflectState(error instanceof ApiError && error.status === 409 ? "busy" : "idle");
      });
  };
  const handleClick = (event: MouseEvent<HTMLDivElement>) => {
    // form covers the reflect input and its gaps, not just the controls
    if ((event.target as HTMLElement).closest("a, button, form")) return;
    open();
  };
  return (
    <article ref={cardRef} className="card fresh-card" onClick={handleClick} data-cursor-target="">
      <PixelBloom />
      <button
        className="delete-note"
        type="button"
        aria-label={`Delete ${note.title}`}
        onClick={() => onDelete(note)}
      >
        ×
      </button>
      {note.has_take ? <span className="take" title="has a take" /> : null}
      {isMemo ? (
        <div className="memocard">
          <div className="memokind">
            {note.kind || "memo"}
            {note.date ? ` · ${note.date}` : ""}
          </div>
          <p>{note.preview || note.title}</p>
          {note.audio ? <MemoWaveform audio={note.audio} /> : null}
          <button className="card-open" type="button" onClick={open}>
            open note
          </button>
        </div>
      ) : note.thumbnail && !imageFailed ? (
        <div className="thumb-wrap">
          <img
            src={`/vault-media/${note.thumbnail}`}
            loading="lazy"
            alt=""
            onLoad={() => setRevealed(true)}
            onError={() => setImageFailed(true)}
          />
          {!revealed ? null : reveal ? (
            <PixelDissolve
              seedKey={note.path}
              cell={22}
              color="var(--bg2)"
              onDone={() => setReveal(false)}
            />
          ) : null}
        </div>
      ) : null}
      {isMemo ? null : (
        <div className="meta">
          <div className="title" onMouseEnter={decode.onMouseEnter}>
            {note.title}
          </div>
          {note.tags.length ? (
            <div className="tags">{note.tags.map((tag) => `#${tag}`).join(" ")}</div>
          ) : null}
          <div className="sub">
            {sourceIcon(note.source)}
            {note.url ? (
              <a href={note.url} target="_blank" rel="noreferrer">
                open
              </a>
            ) : null}
            <button className="card-open" type="button" onClick={open}>
              open note
            </button>
            <button className="card-open" type="button" onClick={ask}>
              {askCopied ? "copied" : "ask"}
            </button>
            <button className="card-open" type="button" onClick={toggleReflect}>
              {reflectState === "reflecting" ? "reflecting" : "reflect"}
            </button>
          </div>
          {reflectOpen ? (
            <form className="mt-[0.4rem] flex items-center gap-[0.4rem]" onSubmit={submitReflection}>
              <input
                className="min-w-0 flex-1 rounded-card border border-line bg-bg1 px-[0.6rem] py-[0.35rem] text-[0.85rem] text-ink placeholder:text-mute focus:border-accent focus:outline-none"
                type="text"
                value={reflectAnswer}
                placeholder={REFLECT_QUESTION}
                onChange={(event) => setReflectAnswer(event.target.value)}
              />
              <button
                className="card-open"
                type="submit"
                disabled={!reflectAnswer.trim() || reflectState === "sending"}
              >
                submit
              </button>
            </form>
          ) : null}
          {reflectState === "busy" ? (
            <div className="mt-[0.2rem] text-[0.78rem] text-mute">one at a time</div>
          ) : null}
        </div>
      )}
    </article>
  );
}
