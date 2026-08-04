import { useState } from "react";
import type { FormEvent, KeyboardEvent, MouseEvent, SyntheticEvent } from "react";
import type { QueueItem } from "../api/queue";
import { reflectAnswer } from "../api/mutations";
import type { ProfileRankPick } from "../api/profileRank";
import { PixelBloom } from "./PixelBloom";
import { sourceIcon } from "./icons";
import { coverAspect } from "../lib/coverAspect";
import { isOpenable, provenance } from "../lib/provenance";
import { capturedLabel } from "../lib/captured";

type ImageStage = "cover" | "preview" | "fallback";
type CardState = "queued" | "ingesting";

/* A card shows the first few lines of a message; the card clips at ~110px
   anyway. Handing the browser the untruncated value is what made the imessage
   filter crawl: an iMessage capture carries whole threads, and 60 of them put
   5,030,431 characters into the DOM — ~84,000 per card, against 70 per card
   for reddit. All of it was shaped and laid out, then hidden by overflow. */
const EXCERPT_CHARS = 400;

function excerpt(text: string | null | undefined): string {
  if (!text) return "";
  return text.length > EXCERPT_CHARS ? `${text.slice(0, EXCERPT_CHARS).trimEnd()}…` : text;
}

function cardClassName(selected?: boolean, state?: CardState, profileMatch?: boolean): string {
  let cls = "card";
  if (selected) cls += " selected";
  if (state) cls += ` ${state}`;
  if (profileMatch) cls += " profile-match";
  return cls;
}

/* What to call this item in an accessible name, in decreasing order of how much
   it actually says. Title first — it is the content's own name, when the item
   has one (#163) — then the body excerpt, then author, and the URL only as a
   last resort, because an Instagram reel id names nothing a reader recognises. */
function itemLabel(item: QueueItem): string {
  if (item.title) return item.title.slice(0, 80);
  const text = excerpt(item.text);
  if (text) return text.slice(0, 80);
  if (item.author) return `${item.source} item by ${item.author}`;
  return item.url;
}

/* Source, place and capture date — the provenance row every card carries,
   including the ones with no usable image, which is the whole point of the
   text-first fallback (#123). */
function CardMeta({ item }: { item: QueueItem }) {
  const place = provenance(item.url).label;
  const captured = capturedLabel(item.shared_at);
  return (
    <div className="sub">
      {sourceIcon(item.source)}
      <span data-testid="card-source">{item.source}</span>
      {place && place !== item.source ? (
        <>
          <span className="sub-dot" aria-hidden="true">
            ·
          </span>
          <span data-testid="card-place">{place}</span>
        </>
      ) : null}
      {item.author ? (
        <>
          <span className="sub-dot" aria-hidden="true">
            ·
          </span>
          <span data-testid="card-author">{item.author}</span>
        </>
      ) : null}
      {captured ? (
        <>
          <span className="sub-dot" aria-hidden="true">
            ·
          </span>
          <time dateTime={item.shared_at} data-testid="card-captured">
            {captured}
          </time>
        </>
      ) : null}
    </div>
  );
}

/* Selection and the original link sit OUTSIDE the inspect target rather than
   inside it. The card used to be one big role="button" with an anchor nested in
   it, which is both invalid and the reason a link click had to be filtered out
   of the card's own handler by hand (#123). */
function CardActions({
  item,
  selected,
  onToggleSelect,
}: {
  item: QueueItem;
  selected: boolean;
  onToggleSelect: (i: QueueItem) => void;
}) {
  return (
    <div className="card-actions">
      <button
        type="button"
        className="card-select"
        role="checkbox"
        aria-checked={selected}
        aria-label={`Select ${itemLabel(item)}`}
        onClick={() => onToggleSelect(item)}
      >
        <span aria-hidden="true">{selected ? "✓" : ""}</span>
      </button>
      {isOpenable(item.url) ? (
        <a
          className="card-origin"
          href={item.url}
          target="_blank"
          rel="noreferrer"
          aria-label={`Open original at ${provenance(item.url).domain || item.source}`}
          title="Open original"
        >
          <span aria-hidden="true">↗</span>
        </a>
      ) : null}
    </div>
  );
}

/* Reflection badge (#98): a sibling of the inspect target, like CardActions,
   so activating it can never bubble into selection or the viewer. Answered
   state flips locally; the queue refetches on its own schedule. */
function CardReflection({ item }: { item: QueueItem }) {
  const [answered, setAnswered] = useState(Boolean(item.reflection_answered));
  const [open, setOpen] = useState(false);
  const [answer, setAnswer] = useState("");
  const question = item.reflection_question;
  if (!question) return null;

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const text = answer.trim();
    // Empty submit on an unanswered item stores nothing; on an answered one it
    // clears the stored answer (the backend's empty-answer semantics).
    if (text || answered) {
      void reflectAnswer(item.url, text);
      setAnswered(Boolean(text));
    }
    setOpen(false);
  };

  return (
    <div className="px-[0.6rem] pb-[0.6rem] font-data text-[12px]">
      <button
        type="button"
        className={`inline-grid h-5 w-5 place-items-center rounded-full border border-line bg-bg3 leading-none ${
          answered ? "text-mute opacity-60" : "text-ink2 hover:border-accent hover:text-accent"
        }`}
        aria-expanded={open}
        aria-label={`${answered ? "Reflection answered" : "Reflection question"}: ${question}`}
        title={question}
        onClick={() => setOpen((v) => !v)}
      >
        ?
      </button>
      {open ? (
        <form onSubmit={handleSubmit}>
          <input
            className="mt-1.5 w-full rounded-[6px] border border-line bg-bg3 px-1.5 py-1 text-ink placeholder:text-mute"
            aria-label={`Answer: ${question}`}
            placeholder={question}
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
          />
        </form>
      ) : null}
    </div>
  );
}

export function Card({
  item,
  onInspect,
  onToggleSelect,
  selected,
  state,
  profileMatch,
}: {
  item: QueueItem;
  onInspect: (i: QueueItem) => void;
  onToggleSelect: (i: QueueItem) => void;
  selected?: boolean | undefined;
  state?: CardState | undefined;
  profileMatch?: ProfileRankPick | undefined;
}) {
  const [stage, setStage] = useState<ImageStage>("cover");

  const handleClick = (e: MouseEvent<HTMLDivElement>) => {
    /* Belt and braces: the actions are siblings of this element now, so a link
       click cannot reach here at all. Kept because a future child link would
       otherwise silently start opening the viewer as well as navigating. */
    if ((e.target as HTMLElement).closest("a, button")) return;
    onInspect(item);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    e.preventDefault();
    onInspect(item);
  };

  const inspectProps = {
    role: "button",
    tabIndex: 0,
    "aria-label": `Inspect ${itemLabel(item)}`,
    onClick: handleClick,
    onKeyDown: handleKeyDown,
  } as const;

  /* Starts as the per-source guess so the card reserves a box before the bytes
     arrive, then yields to the image's own ratio. Holding the guess after load
     would win over the intrinsic size and quietly distort the picture. */
  const [ratio, setRatio] = useState(() => coverAspect(item.source));

  const handleImageLoad = (e: SyntheticEvent<HTMLImageElement>) => {
    const img = e.currentTarget;
    if (!img.naturalWidth || !img.naturalHeight) return;
    setRatio(img.naturalWidth / img.naturalHeight);
  };

  const handleImageError = () => {
    if (stage === "cover") {
      setStage(item.preview_url ? "preview" : "fallback");
    } else if (stage === "preview") {
      setStage("fallback");
    }
  };

  // The only profile-match signal on a card: a quiet theme tag, no score. The
  // number ("match 0.73") read as noise; the theme is the useful part.
  const themeTag = profileMatch ? (
    <span
      className="profile-theme-tag"
      aria-label={`Profile match: ${profileMatch.theme}`}
      title={`Matched ${profileMatch.theme}`}
    >
      {profileMatch.theme}
    </span>
  ) : null;

  if (item.source === "imessage") {
    return (
      <div className={cardClassName(selected, state, Boolean(profileMatch))} data-cursor-target="">
        <CardActions item={item} selected={selected ?? false} onToggleSelect={onToggleSelect} />
        {/* No PixelBloom here. It is a dither that blooms over a cover image,
            and this card has none — it was painting accent cells across the
            message text instead. */}
        <div className="textcard" {...inspectProps}>
          <p>{excerpt(item.text)}</p>
          <div className="textcard-foot">
            <span>{item.author}</span>
          </div>
          {themeTag}
        </div>
        <CardReflection item={item} />
      </div>
    );
  }

  return (
    <div className={cardClassName(selected, state, Boolean(profileMatch))} data-cursor-target="">
      <PixelBloom />
      <CardActions item={item} selected={selected ?? false} onToggleSelect={onToggleSelect} />
      <div className="card-inspect" {...inspectProps}>
        {/* No asset means no image area. The placeholder was 110px of empty box
            captioned with the source name, which the meta row below already
            shows next to its icon — so an imageless Reddit or web item paid for
            a large dead rectangle to repeat one word. Text-first is the useful
            fallback here (#123). */}
        {stage === "fallback" ? null : (
          <img
            src={
              stage === "preview"
                ? item.preview_url
                : `/api/cover?u=${encodeURIComponent(item.url)}`
            }
            /* Reserves the box before the bytes arrive, so the masonry measures
               this card once instead of measuring it empty and re-packing every
               card below it when the image decodes (#22). */
            style={{ aspectRatio: String(ratio) }}
            loading="lazy"
            alt=""
            onError={handleImageError}
            onLoad={handleImageLoad}
          />
        )}
        {state === "ingesting" ? <div className="spinner" /> : null}
        <div className="meta">
          {/* Title, then body excerpt, then a neutral state — never the author
              (creator provenance, not a heading) or the raw URL (#163). */}
          <div className="title">
            {item.title || excerpt(item.text) || (
              <span className="card-untitled text-mute italic">untitled</span>
            )}
          </div>
          <CardMeta item={item} />
          {stage === "fallback" ? <p className="card-nopreview">no preview available</p> : null}
          {themeTag}
        </div>
      </div>
      <CardReflection item={item} />
    </div>
  );
}
