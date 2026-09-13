import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { queryClient } from "../api/client";
import { useAnswerAsk } from "../api/outbox";
import { usePacket } from "../api/packet";
import type { Packet, PacketAsk, PacketView, Round, TrailRow } from "../api/packet";
import { ErrorState } from "../components/StateViews";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "../components/ui/dialog";
import { ago, clockText } from "../lib/packetModel";
import { cn } from "../lib/utils";

/* The packet page (#213): one item, every round, every ask, the trail. A
   HUD of what is in flight, in the hub's skin: no labels unless they carry
   a number, green for here, one alarm red for bounces and mismatches. */

export const Route = createFileRoute("/packet/$id")({ component: PacketPage });

const ALARM = "#e05a6a";
const LIVE = "#4ade80";
const D = "font-data text-[12.5px] tracking-[.04em] lowercase text-ink2 tabular-nums";
const DM = `${D} !text-mute`;
const BIG = "font-normal tracking-[-.02em] leading-none tabular-nums text-ink";
const H2 = "!m-0 !text-lg !font-medium !tracking-[-.02em] !text-ink";
const G2 =
  "grid grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)] items-baseline gap-3 border-b border-line py-[5px] last:border-b-0 [&>*:last-child]:overflow-hidden [&>*:last-child]:text-ellipsis [&>*:last-child]:whitespace-nowrap";
const G3 =
  "grid grid-cols-[62px_minmax(0,1fr)_auto] items-baseline gap-3 border-b border-line py-[5px] last:border-b-0 [&>*:nth-child(2)]:overflow-hidden [&>*:nth-child(2)]:text-ellipsis [&>*:nth-child(2)]:whitespace-nowrap";
const UNIT = "text-accent font-data text-[12.5px] tracking-[.04em] tabular-nums";
const UNIT_BTN = `${UNIT} appearance-none border-0 bg-transparent p-0 cursor-pointer border-b border-dotted border-accent/50 hover:text-ink hover:border-ink`;
const PLATE =
  "relative before:content-[''] before:absolute before:-top-px before:-left-px before:size-3 before:border-t before:border-l before:border-ink2 before:opacity-80 after:content-[''] after:absolute after:-bottom-px after:-right-px after:size-3 after:border-b after:border-r after:border-ink2 after:opacity-80";
const OPT =
  "inline-block rounded-full border border-line px-2.5 py-px mr-1 my-0.5 font-data text-xs tracking-[.04em] text-ink2";

const UNIT_RE = /t:\d+(?:-\d+)?|frame:\d+/g;

function useNow(fixed: string | undefined): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (fixed) return;
    const i = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(i);
  }, [fixed]);
  return fixed ? Date.parse(fixed) : now;
}

const hhmm = (iso: string) => clockText(Date.parse(iso));
const modelRow = (m: Round["writer"]) =>
  m
    ? `${(m.model ?? "").replace("claude-", "")} · ${m.tokens.toLocaleString()} tok · ${m.seconds} s`
    : "";

/* Every t:<s> and frame:NNN in a finding, bounce or spot check is a link. */
function Units({
  text,
  onUnit,
  className,
}: {
  text: string;
  onUnit: (u: string) => void;
  className?: string;
}) {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(UNIT_RE)) {
    if (m.index! > last) parts.push(text.slice(last, m.index));
    const u = m[0];
    parts.push(
      <button
        key={`${m.index}-${u}`}
        type="button"
        className={UNIT_BTN}
        data-unit={u}
        onClick={() => onUnit(u)}
      >
        {u}
      </button>,
    );
    last = m.index! + u.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <span className={className}>{parts.length ? parts : "—"}</span>;
}

function PadSvg({ n, cap, running }: { n: number; cap: number; running: boolean }) {
  const m = Math.min(cap, n);
  return (
    <svg
      width={cap * 22}
      height="8"
      viewBox={`0 0 ${cap * 22} 8`}
      className="block"
      aria-label={`${n} of ${cap} calls`}
    >
      {Array.from({ length: cap }, (_, i) => (
        <rect
          key={i}
          x={i * 22}
          y="0"
          width="18"
          height="8"
          rx="2"
          fill={i < m ? (n > cap ? ALARM : "var(--accent)") : i === m && running ? LIVE : "#3a3a42"}
        />
      ))}
    </svg>
  );
}

/* The strip: the transcript span with spot checks above it, the frame rail
   below with shown, not shown and bounced frames. */
function Strip({ v, round }: { v: PacketView | null; round: Round | undefined }) {
  const w = 330;
  if (!v || !v.duration)
    return <div className={DM}>no transcript in this packet · {v ? v.nframes : 0} frames</div>;
  const dur = v.duration;
  const spots: ReactNode[] = [];
  const bad = new Set<number>();
  if (round)
    for (const s of round.spots) {
      for (const m of s.where.matchAll(/t:(\d+)(?:-(\d+))?/g)) {
        const a = +m[1]!,
          b = +(m[2] ?? m[1]!);
        const xa = (a / dur) * w,
          xb = (Math.max(a + 1, b) / dur) * w;
        spots.push(
          <rect
            key={`${s.where}-${a}`}
            x={xa.toFixed(1)}
            y="4"
            width={Math.max(2, xb - xa).toFixed(1)}
            height="6"
            rx="1"
            fill={s.grounded ? "var(--accent)" : ALARM}
          />,
        );
      }
      if (!s.grounded) for (const m of s.where.matchAll(/frame:(\d+)/g)) bad.add(+m[1]!);
    }
  const nf = v.nframes;
  const shownF = new Set(v.shown.filter((u) => u.startsWith("frame:")).map((u) => +u.slice(6)));
  const frames: ReactNode[] = [];
  if (nf) {
    const fw = w / nf;
    for (let i = 1; i <= nf; i++) {
      const shown = shownF.has(i);
      const h = shown ? 10 : 6;
      frames.push(
        <rect
          key={i}
          x={((i - 1) * fw + 1).toFixed(1)}
          y={40 - h}
          width={Math.max(1.5, fw - 2).toFixed(1)}
          height={h}
          rx="1"
          fill={bad.has(i) ? ALARM : shown ? "var(--accent)" : "#3a3a42"}
        />,
      );
    }
  }
  return (
    <svg
      width={w}
      height="56"
      viewBox={`0 0 ${w} 56`}
      className="block max-w-full overflow-visible"
      aria-label="the packet on the source timeline"
    >
      <rect x="0" y="14" width={w} height="6" fill="var(--accent)" fillOpacity=".85" />
      {spots}
      {frames}
      {(
        [
          ["0", 0],
          [String(Math.round(dur / 2)), dur / 2],
          [`${Math.round(dur)} s`, dur],
        ] as const
      ).map(([lab, sec]) => (
        <text
          key={lab}
          x={((sec / dur) * w).toFixed(1)}
          y="52"
          fontSize="10"
          fill="#83817a"
          textAnchor={sec === dur ? "end" : sec === 0 ? "start" : "middle"}
          fontFamily="Newsreader, Georgia, serif"
        >
          {lab}
        </text>
      ))}
    </svg>
  );
}

function PacketColumn({
  p,
  onUnit,
  flash,
  lineRefs,
  onFrame,
}: {
  p: Packet;
  onUnit: (u: string) => void;
  flash: number | null;
  lineRefs: React.MutableRefObject<Map<number, HTMLDivElement>>;
  onFrame: (id: string, url: string) => void;
}) {
  const v = p.view;
  const lastClosed = [...p.attempts].reverse().find((a) => a.closed_at);
  const framesShown = v ? v.shown.filter((u) => u.startsWith("frame:")).length : 0;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <h2 className={H2}>packet</h2>
        <span className={DM}>the view, immutable</span>
      </div>
      <div className="flex flex-col gap-1">
        <div className={`${DM} flex justify-between`}>
          <span>on the source timeline · spot checks above</span>
          <span>{lastClosed ? `attempt ${lastClosed.n}` : ""}</span>
        </div>
        <Strip v={v} round={lastClosed} />
        {v?.nframes ? (
          <div className={DM}>
            frames, {framesShown} shown of {v.nframes}
          </div>
        ) : null}
      </div>
      {v ? (
        <div className="flex flex-col">
          <div className={`${DM} flex justify-between pb-1`}>
            <span>units</span>
            <span>weight</span>
          </div>
          {v.shown.map((u) => (
            <div key={u} className={G2}>
              <span className={UNIT}>{u}</span>
              <span className={`${D} text-right`}>
                {u.startsWith("t:") ? `${v.nlines} lines · ${v.origin}` : "frame · sparse"}
              </span>
            </div>
          ))}
          {v.openable.map((u) => (
            <div key={u} className={G2}>
              <span className={UNIT}>{u}</span>
              <span className={`${D} text-right`}>in the box</span>
            </div>
          ))}
          {v.not_shown.map((u) => (
            <div key={u} className={G2}>
              <span className={`${D} !text-mute`}>{u}</span>
              <span className={`${DM} text-right`}>not shown</span>
            </div>
          ))}
          <div className={G2}>
            <span className={DM}>budget</span>
            <span className={`${D} text-right`}>
              {v.budget.frames_shown} frames · {(v.budget.evidence_cap_chars ?? 0).toLocaleString()}{" "}
              chars · sheet {v.budget.sheet}
            </span>
          </div>
          <div className={G2}>
            <span className={DM}>tokenizer</span>
            <span className={`${D} text-right`}>{v.tokenizer}</span>
          </div>
        </div>
      ) : (
        <div className={DM}>
          this item has no packet on disk: it was graded before #212 or never enriched
        </div>
      )}
      {v?.lines.length ? (
        <div className="flex flex-col gap-1">
          <div className={`${DM} flex justify-between`}>
            <span>
              unit t:0-{Math.round(v.duration ?? 0)} · the lines the teacher cited are lit
            </span>
            <span>{v.nlines} lines</span>
          </div>
          <div
            className="flex max-h-[380px] flex-col gap-px overflow-auto rounded-md bg-bg1 px-1 py-2"
            data-testid="transcript"
          >
            {v.lines.map((l, i) =>
              "fold" in l ? (
                <div
                  key={`f${i}`}
                  className="grid grid-cols-[34px_minmax(0,1fr)] gap-3 px-1.5 text-[12.5px] text-mute"
                >
                  <span className="text-right">…</span>
                  <span>{l.fold} lines folded</span>
                </div>
              ) : (
                <div
                  key={l.s}
                  ref={(el) => {
                    if (el) lineRefs.current.set(l.s, el);
                    else lineRefs.current.delete(l.s);
                  }}
                  data-second={l.s}
                  className={cn(
                    "grid grid-cols-[34px_minmax(0,1fr)] gap-3 rounded-[3px] px-1.5 py-px text-sm leading-[1.45]",
                    l.hit && "bg-accent/15",
                    flash === l.s && "bg-live/20",
                  )}
                >
                  <span className="pt-0.5 text-right text-xs text-mute tabular-nums">{l.s}</span>
                  <span>{l.text}</span>
                </div>
              ),
            )}
          </div>
        </div>
      ) : null}
      {v?.frames.length ? (
        <div className="flex flex-col gap-1.5">
          <div className="flex gap-2.5">
            {v.frames.map((f) => (
              <button
                key={f.id}
                type="button"
                className="appearance-none border-0 bg-transparent p-0 cursor-zoom-in min-w-0 flex-1"
                onClick={() => onFrame(f.id, f.url)}
                aria-label={`open ${f.id}`}
              >
                <img src={f.url} alt={f.id} className="block w-full rounded border border-line" />
              </button>
            ))}
          </div>
          <div className={`${DM} flex justify-between`}>
            {v.frames.map((f) => (
              <button key={f.id} type="button" className={UNIT_BTN} onClick={() => onUnit(f.id)}>
                {f.id}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function RoundBlock({
  a,
  now,
  folded,
  onToggle,
  onUnit,
}: {
  a: Round;
  now: number;
  folded: boolean;
  onToggle: () => void;
  onUnit: (u: string) => void;
}) {
  const closed = a.closed_at != null && Date.parse(a.closed_at) <= now;
  const col = closed ? (a.passed ? "var(--ink)" : ALARM) : LIVE;
  const mismatch = a.marker?.view_hash && a.marker.view_hash !== a.view_hash;
  return (
    <div
      className={cn(
        "flex flex-col gap-2 rounded-lg border border-line px-3.5 py-3",
        !closed && "border-live",
      )}
      data-round={a.n}
      data-folded={folded ? "1" : "0"}
    >
      <button
        type="button"
        className="flex cursor-pointer appearance-none items-baseline justify-between border-0 bg-transparent p-0 text-left font-serif text-base text-ink"
        onClick={onToggle}
        aria-expanded={!folded}
      >
        <span>
          attempt {a.n}{" "}
          <span className={D} style={{ color: col }}>
            {closed
              ? a.passed
                ? "pass"
                : `bounce · ${a.bounces.map((b) => b.check).join(", ")}`
              : "writing"}
          </span>
        </span>
        <span className={DM}>
          {closed && a.closed_at
            ? `${hhmm(a.opened_at)} to ${hhmm(a.closed_at)}`
            : `opened ${hhmm(a.opened_at)}`}
          {folded ? " · open" : ""}
        </span>
      </button>
      {folded ? null : (
        <>
          <div className={DM}>
            findings in · {a.findings.length}
            {a.findings.length ? "" : " · a blind first draft"}
          </div>
          {a.findings.length ? (
            <div className="flex flex-col">
              {a.findings.map((f, i) => (
                <div key={i} className={G2} title={f.detail}>
                  <span className={D}>{f.check}</span>
                  <Units text={f.where} onUnit={onUnit} className={`${DM} text-right`} />
                </div>
              ))}
            </div>
          ) : null}
          <div className={DM}>
            draft out
            {a.writer && Date.parse(a.writer.at) <= now ? ` · ${modelRow(a.writer)}` : " · writing"}
            {a.take_kind ? ` · take ${a.take_kind}` : ""}
          </div>
          {a.draft?.thesis && closed ? (
            <>
              <div className="text-sm leading-[1.35] text-ink2">{a.draft.thesis}</div>
              <div className={DM}>
                {a.draft.concepts} concepts · {a.draft.insights} insights · {a.draft.moments}{" "}
                moments
                {a.draft.tags.length ? ` · ${a.draft.tags.slice(0, 5).join(", ")}` : ""}
              </div>
            </>
          ) : null}
          <div className={DM}>
            verdict{a.marker && Date.parse(a.marker.at) <= now ? ` · ${modelRow(a.marker)}` : ""}
            {closed ? (
              <>
                {" · packet "}
                <span
                  className="tabular-nums"
                  style={{ color: mismatch ? ALARM : "var(--accent)" }}
                >
                  {a.view_hash}
                </span>
                {a.marker?.view_hash
                  ? mismatch
                    ? ` differs from ${a.marker.view_hash}`
                    : " same"
                  : ""}
              </>
            ) : (
              " · not yet"
            )}
          </div>
          {closed ? (
            <div className="flex flex-col">
              {a.bounces.map((b, i) => (
                <div key={`b${i}`} className={G2} title={b.detail}>
                  <span className={D} style={{ color: ALARM }}>
                    bounce · {b.check}
                  </span>
                  <Units text={b.where} onUnit={onUnit} className={`${DM} text-right`} />
                </div>
              ))}
              {a.spots.map((s, i) => (
                <div key={`s${i}`} className={G2} title={s.claim}>
                  <span className={D} style={s.grounded ? undefined : { color: ALARM }}>
                    spot check · {s.grounded ? "grounded" : "not grounded"}
                  </span>
                  <Units text={s.where} onUnit={onUnit} className={`${D} text-right`} />
                </div>
              ))}
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

function AskBlock({
  k,
  now,
  saying,
  onSay,
  onAnswer,
  pending,
}: {
  k: PacketAsk;
  now: number;
  saying: boolean;
  onSay: (open: boolean) => void;
  onAnswer: (choice: string, text?: string) => void;
  pending: boolean;
}) {
  const [text, setText] = useState("");
  const open = !k.answer;
  return (
    <div
      className={cn(
        "flex flex-col gap-1.5 rounded-lg border border-line px-3 py-2.5",
        open && "border-accent",
      )}
      data-ask={k.id}
    >
      <div className="flex items-baseline justify-between">
        <span className="text-[14.5px]">
          {k.kind}
          {open ? <span className={`${D} !text-accent`}> open</span> : null}
        </span>
        <span className={DM}>
          {hhmm(k.created_at)}
          {k.attempt ? ` · attempt ${k.attempt}` : ""}
        </span>
      </div>
      {k.why ? <div className="text-[13px] leading-[1.35] text-ink2">{k.why}</div> : null}
      <div>
        {k.options.map((o, i) =>
          open ? (
            <button
              key={o}
              type="button"
              className={`${OPT} cursor-pointer bg-transparent hover:border-white/30 hover:text-ink`}
              disabled={pending}
              onClick={() =>
                o === "say what is wrong" ? onSay(true) : onAnswer(o, text.trim() || undefined)
              }
            >
              {i < 4 ? (
                <span className="mr-1.5 rounded border border-line px-[5px] text-xs">{i + 1}</span>
              ) : null}
              {o}
            </button>
          ) : (
            <span
              key={o}
              className={cn(OPT, k.answer?.choice === o && "border-accent bg-accent/10 text-ink")}
            >
              {o}
            </span>
          ),
        )}
      </div>
      {open && saying ? (
        <textarea
          className="min-h-16 w-full resize-y rounded-md border border-line bg-bg1 p-2 font-serif text-[13.5px] text-ink"
          placeholder="what is wrong, in your words · enter to send, esc to cancel"
          value={text}
          autoFocus
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onAnswer("say what is wrong", text.trim());
            }
            if (e.key === "Escape") {
              e.stopPropagation();
              onSay(false);
            }
          }}
        />
      ) : null}
      <div className={DM}>
        {k.answer
          ? `answered ${hhmm(k.answer.at)} · ${k.answer.choice}${k.answer.text ? ` · “${k.answer.text.slice(0, 80)}”` : ""}`
          : Date.parse(k.created_at) <= now
            ? "waiting for the owner · pick an option, or press its number"
            : ""}
      </div>
    </div>
  );
}

function Trail({
  rows,
  station,
  now,
  all,
  onToggle,
}: {
  rows: TrailRow[];
  station: Packet["station"];
  now: number;
  all: boolean;
  onToggle: () => void;
}) {
  const shown = all ? rows : rows.slice(-8);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <h2 className={H2}>trail</h2>
        <span className={DM}>
          register · {rows.length} hand-offs
          {rows.length > 8 ? (
            <>
              {" · "}
              <button type="button" className={UNIT_BTN} onClick={onToggle}>
                {all ? "last eight" : "show all"}
              </button>
            </>
          ) : null}
        </span>
      </div>
      <div className="flex flex-col">
        {shown.map((r, i) => (
          <div key={`${r.at}-${i}`} className={G3}>
            <span className={DM} style={r.error ? { color: ALARM } : undefined}>
              {hhmm(r.at)}
            </span>
            <span className={D} style={r.error ? { color: ALARM } : undefined}>
              {r.who} · {r.what}
            </span>
            <span className={`${DM} text-right`}>{r.right}</span>
          </div>
        ))}
        {station?.name === "student" ? (
          <div className={G3}>
            <span className={D} style={{ color: LIVE }}>
              {clockText(now)}
            </span>
            <span className={D} style={{ color: LIVE }}>
              student · {station.note}
            </span>
            <span className={`${D} text-right`} style={{ color: LIVE }}>
              writing
            </span>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function PacketPage() {
  const { id } = Route.useParams();
  const { t } = Route.useSearch();
  const itemId = Number(id);
  const q = usePacket(itemId, t);
  const now = useNow(t);
  const answer = useAnswerAsk();
  const [open, setOpen] = useState<Set<number>>(new Set());
  const [trailAll, setTrailAll] = useState(false);
  const [saying, setSaying] = useState<number | null>(null);
  const [flash, setFlash] = useState<number | null>(null);
  const [frame, setFrame] = useState<{ id: string; url: string } | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const lineRefs = useRef(new Map<number, HTMLDivElement>());
  const p = q.data;

  useEffect(() => {
    if (!toast) return;
    const i = setTimeout(() => setToast(null), 1600);
    return () => clearTimeout(i);
  }, [toast]);
  useEffect(() => {
    if (flash == null) return;
    const i = setTimeout(() => setFlash(null), 1400);
    return () => clearTimeout(i);
  }, [flash]);

  const goUnit = (u: string) => {
    if (u.startsWith("frame:")) {
      const f = p?.view?.frames.find((x) => x.id === u);
      if (f) setFrame({ id: f.id, url: f.url });
      else setToast(`${u} · not in this packet`);
      return;
    }
    const sec = +u.slice(2).split("-")[0]!;
    const secs = [...lineRefs.current.keys()];
    if (!secs.length) {
      setToast(`${u} · no transcript in this packet`);
      return;
    }
    const best = secs.reduce((a, b) => (Math.abs(b - sec) < Math.abs(a - sec) ? b : a));
    lineRefs.current.get(best)?.scrollIntoView({ block: "center", behavior: "smooth" });
    setFlash(best);
  };

  const send = (k: PacketAsk, choice: string, text?: string) => {
    answer.mutate(text ? { ask_id: k.id, choice, text } : { ask_id: k.id, choice }, {
      onSuccess: () => {
        setSaying(null);
        setToast(`ask ${k.id} · ${choice}`);
        void queryClient.invalidateQueries({ queryKey: ["packet"] });
      },
    });
  };

  const plain = useMemo(() => (p?.asks ?? []).filter((k) => k.kind !== "connections"), [p]);
  const links = useMemo(() => (p?.asks ?? []).filter((k) => k.kind === "connections"), [p]);
  const firstOpen = plain.find((k) => !k.answer);

  // 1 to 4 answer the oldest open ask; the layout owns j, k and esc.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || frame) return;
      if (!/^[1-4]$/.test(e.key) || !firstOpen) return;
      const o = firstOpen.options[+e.key - 1];
      if (!o) return;
      if (o === "say what is wrong") setSaying(firstOpen.id);
      else send(firstOpen, o);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firstOpen, frame]);

  const copy = async (cmd: string) => {
    try {
      await navigator.clipboard.writeText(cmd);
      setToast(`copied · ${cmd}`);
    } catch {
      setToast(cmd);
    }
  };

  if (q.isError)
    return (
      <div className="px-7 pt-4">
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      </div>
    );
  if (!p) return <p className={`${DM} px-7 pt-4`}>loading {itemId}</p>;

  const s = p.station;
  const stationName = s ? s.name : "filed";
  const held = s ? Math.max(0, (now - Date.parse(s.since)) / 1000) : 0;
  const lastN = p.attempts.length ? p.attempts[p.attempts.length - 1]!.n : 0;
  const agreement = p.agreement;

  return (
    <div className="mx-auto box-border w-full max-w-[1440px] px-4 pt-4 sm:px-7">
      <div
        className={`${PLATE} box-border flex flex-col gap-[18px] border border-line bg-bg2 px-[22px] py-5`}
        data-testid="packet-page"
      >
        <div className="flex flex-wrap items-end justify-between gap-6 border-b border-line pb-3.5">
          <div className="flex min-w-0 items-baseline gap-3.5">
            <span className={`${BIG} text-[40px]`}>{p.id}</span>
            <div className="flex min-w-0 flex-col gap-[3px]">
              <span className="text-[17px]">{p.title}</span>
              <span className={D}>
                {p.source}
                {p.view ? (
                  <>
                    {" · "}
                    {p.view.origin || "no transcript"} · packet{" "}
                    <span className="text-accent">{p.view.hash}</span> · bundle {p.view.bundle}
                  </>
                ) : (
                  " · no packet on disk"
                )}
              </span>
              <span className="text-[13.5px] text-ink2 italic">
                {p.take ? `the sticky note, ${p.take.kind}: ${p.take.text}` : "no sticky note"}
              </span>
            </div>
          </div>
          <div className="flex flex-none flex-wrap items-end gap-7">
            <div className="flex flex-col items-end gap-[5px]">
              <span
                className={`${BIG} text-[28px]`}
                style={{ color: s?.model ? LIVE : "var(--ink)" }}
                data-testid="station"
              >
                {stationName}
              </span>
              <span className={DM}>{s ? `${s.note} · ${ago(held)}` : "on the shelf"}</span>
            </div>
            <div className="flex flex-col items-end gap-[5px]">
              <PadSvg n={p.calls} cap={p.cap} running={p.running} />
              <span className={DM}>
                {p.calls > p.cap
                  ? `${p.calls} calls, ${p.calls - p.cap} past the pad of ${p.cap}`
                  : `${p.calls} of ${p.cap} calls`}
                {p.running ? ", one running" : ""} · {p.tokens.toLocaleString()} tokens
              </span>
            </div>
            <div className="flex flex-col items-end gap-[5px]" data-testid="agreement">
              <span
                className={`${D} text-sm`}
                style={{
                  color:
                    agreement.status === "same"
                      ? LIVE
                      : agreement.status === "mismatch"
                        ? ALARM
                        : "var(--mute)",
                }}
              >
                {agreement.status === "same"
                  ? "same packet"
                  : agreement.status === "mismatch"
                    ? "packet mismatch"
                    : agreement.status === "none"
                      ? "no packet hash on the grade"
                      : "not graded yet"}
              </span>
              <span className={DM}>
                {agreement.status === "same" || agreement.status === "mismatch"
                  ? `draft ${agreement.draft} · grade ${agreement.grade}`
                  : agreement.status === "none"
                    ? "graded before the packet model"
                    : agreement.draft
                      ? `draft reads ${agreement.draft}`
                      : ""}
              </span>
            </div>
            <div className="flex gap-1.5">
              {(
                [
                  ["view", p.commands.view],
                  ["grade again", p.commands.grade],
                  ["item", p.commands.item],
                ] as const
              ).map(([l, c]) => (
                <Button key={l} size="sm" variant="outline" title={c} onClick={() => void copy(c)}>
                  {l}
                </Button>
              ))}
            </div>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-[26px] lg:grid-cols-[minmax(0,1fr)_minmax(0,1.45fr)_minmax(0,1fr)]">
          <PacketColumn
            p={p}
            onUnit={goUnit}
            flash={flash}
            lineRefs={lineRefs}
            onFrame={(fid, url) => setFrame({ id: fid, url })}
          />
          <div className="flex flex-col gap-3">
            <div className="flex items-baseline justify-between">
              <h2 className={H2}>rounds</h2>
              <span className={DM}>
                {p.attempts.length
                  ? `${p.attempts.length} on disk · findings in, draft out, verdict out`
                  : ""}
              </span>
            </div>
            <div className="flex flex-col gap-3">
              {p.attempts.length ? (
                p.attempts.map((a) => (
                  <RoundBlock
                    key={a.n}
                    a={a}
                    now={now}
                    folded={(a.n !== lastN) !== open.has(a.n)}
                    onToggle={() =>
                      setOpen((prev) => {
                        const next = new Set(prev);
                        if (next.has(a.n)) next.delete(a.n);
                        else next.add(a.n);
                        return next;
                      })
                    }
                    onUnit={goUnit}
                  />
                ))
              ) : (
                <div className={DM}>no round yet</div>
              )}
            </div>
          </div>
          <div className="flex flex-col gap-[18px]">
            <div className="flex flex-col gap-2.5">
              <div className="flex items-baseline justify-between">
                <h2 className={H2}>asks</h2>
                <span className={DM}>
                  {plain.length ? `${plain.length} raised` : "none raised"}
                </span>
              </div>
              {plain.map((k) => (
                <AskBlock
                  key={k.id}
                  k={k}
                  now={now}
                  saying={saying === k.id}
                  onSay={(o) => setSaying(o ? k.id : null)}
                  onAnswer={(c, text) => send(k, c, text)}
                  pending={answer.isPending}
                />
              ))}
              {answer.isError ? (
                <p className={`${D} !text-accent m-0`} role="alert">
                  answer failed: {String(answer.error)}
                </p>
              ) : null}
            </div>
            {links.length ? (
              <div className="flex flex-col gap-2.5">
                <div className="flex items-baseline justify-between">
                  <h2 className={H2}>connections</h2>
                  <span className={DM}>
                    the librarian argued {links.reduce((n, k) => n + k.links.length, 0)}
                  </span>
                </div>
                {links.map((k) => (
                  <div
                    key={k.id}
                    className="flex flex-col gap-1.5 rounded-lg border border-line px-3 py-2.5"
                  >
                    <div className="flex items-baseline justify-between">
                      <span className={D}>{hhmm(k.created_at)}</span>
                      <span className={DM}>
                        {k.answer ? `answered ${hhmm(k.answer.at)} · ${k.answer.choice}` : "open"}
                      </span>
                    </div>
                    {k.links.map((l, i) => (
                      <div key={i} className={G2} title={l.why}>
                        <span
                          className={D}
                          style={{
                            color: k.answer?.choice === "approve" ? "var(--ink)" : undefined,
                          }}
                        >
                          {l.title}
                        </span>
                        <span className={`${DM} text-right`}>
                          {k.answer?.choice === "approve"
                            ? "approved"
                            : k.answer
                              ? k.answer.choice
                              : "argued"}
                        </span>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            ) : null}
            <Trail
              rows={p.trail}
              station={s}
              now={now}
              all={trailAll}
              onToggle={() => setTrailAll((v) => !v)}
            />
          </div>
        </div>
        <div className="flex flex-wrap items-end justify-between gap-4 border-t border-line pt-3.5">
          <div className="flex items-baseline gap-3">
            <span className={`${BIG} text-[36px]`}>{p.rounds || ""}</span>
            <div className="flex flex-col gap-0.5">
              <span className="text-[15px]">
                {p.rounds
                  ? `attempt · at the ${stationName === "filed" ? "shelf" : stationName}`
                  : s
                    ? `at the ${stationName}`
                    : "filed"}
              </span>
              <span className={DM}>{s ? `${s.note} · ${ago(held)}` : ""}</span>
            </div>
          </div>
          <a
            href={p.url}
            target="_blank"
            rel="noreferrer"
            className={`${DM} no-underline hover:!text-ink`}
          >
            {p.url}
          </a>
        </div>
      </div>
      <Dialog open={frame != null} onOpenChange={(o) => !o && setFrame(null)}>
        <DialogContent
          className="flex w-auto max-w-[min(92vw,1100px)] flex-col items-center gap-2.5 bg-transparent p-0"
          onClick={() => setFrame(null)}
        >
          <DialogTitle className="sr-only">{frame?.id ?? "frame"}</DialogTitle>
          {frame ? (
            <img
              src={frame.url}
              alt={frame.id}
              className="max-h-[80vh] max-w-full rounded border border-white/15"
            />
          ) : null}
          <span className={D}>
            {frame?.id} · packet {p.view?.hash ?? ""}
          </span>
        </DialogContent>
      </Dialog>
      {toast ? (
        <div
          className="fixed right-5 bottom-5 z-30 rounded-md border border-accent bg-bg2 px-3 py-2 text-[13px] text-ink"
          role="status"
        >
          {toast}
        </div>
      ) : null}
    </div>
  );
}
