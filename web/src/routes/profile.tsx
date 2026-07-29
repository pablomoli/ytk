import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useProfile, useRunProfile } from "../api/profile";
import type { ProfileExemplar, ProfileTheme } from "../api/profile";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { HubControls } from "../components/HubControls";
import { sourceIcon } from "../components/icons";
import { ErrorState } from "../components/StateViews";
import "../styles.css";

export const Route = createFileRoute("/profile")({ component: ProfilePage });

/* Spectrum bands cycle three brass steps; color is texture, never the
   identifier. Identity is the rank numeral — the same number prefixes the
   theme's row below, and choose_k keeps the distribution flat by design, so
   most bands will never be wide enough to carry their label. */
const BAND_CLASSES = ["bg-accent", "bg-accent/55", "bg-accent/30"];

function Thumb({ exemplar, className }: { exemplar: ProfileExemplar; className: string }) {
  if (!exemplar.thumb) return null;
  return (
    <img
      src={`/vault-media/${exemplar.thumb}`}
      alt=""
      loading="lazy"
      className={`${className} rounded-[4px] border border-line object-cover bg-bg3`}
    />
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[1.7rem] leading-none tabular-nums text-ink">{value}</span>
      <span className="stat text-mute mt-1">{label}</span>
    </div>
  );
}

function ThemeRow({
  theme,
  rank,
  maxWeight,
}: {
  theme: ProfileTheme;
  rank: number;
  maxWeight: number;
}) {
  const share = Math.round(theme.weight * 100);
  const scale = theme.weight / maxWeight;
  const fresh = theme.fresh_notes ?? 0;
  const freshFrac = theme.n_notes ? fresh / theme.n_notes : 0;
  const strip = theme.exemplars.filter((e) => e.thumb);
  return (
    <details className="profile-theme group border-b border-line py-2">
      <summary className="grid cursor-pointer list-none items-center gap-x-4 [grid-template-columns:minmax(11rem,17rem)_1fr_max-content_8.5rem]">
        <span className="text-[1.02rem] text-ink">
          <span className="count mr-2 inline-block w-5 text-right text-mute">{rank}</span>
          {theme.label}
        </span>
        <span
          className="profile-theme-bar relative h-[7px] overflow-hidden rounded-full bg-bg3"
          role="meter"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={share}
          aria-label={`${theme.label} weight`}
        >
          {/* two lightnesses of one hue: recent vs older notes; the numbers
              beside the bar carry the exact split */}
          <span
            className="absolute inset-y-0 left-0 rounded-full bg-accent/35"
            style={{ width: `${scale * 100}%` }}
          />
          <span
            className="absolute inset-y-0 left-0 rounded-full bg-accent"
            style={{ width: `${scale * freshFrac * 100}%` }}
          />
        </span>
        <span className="count text-mute">
          {share}% · {theme.n_notes} notes
          {fresh && fresh < theme.n_notes ? ` · ${fresh} recent` : ""}
        </span>
        <span className="flex justify-end -space-x-2">
          {strip.map((exemplar) => (
            <Thumb
              key={exemplar.title}
              exemplar={exemplar}
              className="h-7 w-12 shrink-0 transition-transform duration-200 ease-hub group-open:scale-0 group-open:w-0"
            />
          ))}
        </span>
      </summary>
      <div className="grid gap-x-8 gap-y-2 pb-3 pt-2 md:[grid-template-columns:minmax(0,1fr)_max-content]">
        <p className="m-0 max-w-[52ch] text-ink2">{theme.summary}</p>
        {theme.exemplars.length ? (
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {theme.exemplars.map((exemplar) => (
              <li key={exemplar.title} className="profile-exemplar flex items-center gap-2.5">
                <Thumb exemplar={exemplar} className="h-9 w-16" />
                {exemplar.source ? sourceIcon(exemplar.source) : null}
                <span className="sub text-ink2">{exemplar.title}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </details>
  );
}

function ProfilePage() {
  const profile = useProfile();
  const run = useRunProfile();
  const [confirmSynth, setConfirmSynth] = useState(false);

  if (profile.isLoading)
    return (
      <div className="hub-page">
        <div className="hub-body">loading profile...</div>
      </div>
    );

  const resynthesize = () => setConfirmSynth(true);

  const controls = (
    <HubControls>
      <button className="btn" type="button" onClick={resynthesize} disabled={run.isPending}>
        {run.isPending ? "synthesizing..." : "re-synthesize"}
      </button>
    </HubControls>
  );

  const confirmDialog = confirmSynth ? (
    <ConfirmDialog
      message="re-synthesize the interest profile? one claude call; takes up to a minute."
      confirmLabel="synthesize"
      onCancel={() => setConfirmSynth(false)}
      onConfirm={() => {
        setConfirmSynth(false);
        run.mutate();
      }}
    />
  ) : null;

  if (profile.isError) {
    return (
      <div className="hub-page">
        {controls}
        <div className="hub-body">
          <ErrorState error={profile.error} />
          <p className="text-mute">no snapshot yet — re-synthesize to build one.</p>
        </div>
        {confirmDialog}
      </div>
    );
  }

  const data = profile.data!;
  const maxWeight = Math.max(...data.themes.map((theme) => theme.weight), 0.0001);
  const totalWeight = data.themes.reduce((sum, theme) => sum + theme.weight, 0) || 1;
  const totalNotes = data.themes.reduce((sum, theme) => sum + theme.n_notes, 0);
  const freshNotes = data.themes.reduce((sum, theme) => sum + (theme.fresh_notes ?? 0), 0);
  const portrait = data.claims?.length
    ? data.claims.map((claim) => claim.text)
    : data.profile_markdown.split(/\n\n+/).filter(Boolean);

  return (
    <div id="profile-page" className="hub-page">
      {controls}
      <div className="hub-body">
        <div className="flex flex-wrap items-end gap-x-10 gap-y-4 pt-2">
          <Stat value={String(data.note_count)} label="notes" />
          <Stat value={String(data.themes.length)} label="themes" />
          <Stat
            value={totalNotes ? `${Math.round((freshNotes / totalNotes) * 100)}%` : "—"}
            label="recent"
          />
          <p className="meta-line m-0 ml-auto self-end text-mute">
            synthesized {data.generated_at.slice(0, 16).replace("T", " ")}
            {data.embedding_model ? ` · ${data.embedding_model.split("/").pop()}` : ""}
            {data.reanchored_from ? " · re-anchored across an encoder swap" : ""}
          </p>
        </div>

        <div
          className="flex h-9 w-full gap-[2px] overflow-hidden rounded-[6px]"
          role="img"
          aria-label="share of attention by theme, numbered by rank"
        >
          {data.themes.map((theme, i) => {
            const pct = (theme.weight / totalWeight) * 100;
            return (
              <span
                key={theme.id}
                title={`${i + 1} · ${theme.label} — ${Math.round(theme.weight * 100)}%`}
                className={`${BAND_CLASSES[i % BAND_CLASSES.length]} flex min-w-[1.4rem] items-center gap-1.5 overflow-hidden px-1.5`}
                style={{ flexGrow: pct, flexBasis: 0 }}
              >
                <span className="count shrink-0 !text-bg0">{i + 1}</span>
                {pct > 8 ? <span className="stat truncate !text-bg0/80">{theme.label}</span> : null}
              </span>
            );
          })}
        </div>

        <div className="grid items-start gap-x-14 gap-y-8 lg:[grid-template-columns:minmax(0,7fr)_minmax(20rem,3fr)]">
          <section className="profile-themes">
            <h2 className="stat m-0 pb-2 text-mute">attention by theme</h2>
            {data.themes.map((theme, i) => (
              <ThemeRow key={theme.id} theme={theme} rank={i + 1} maxWeight={maxWeight} />
            ))}
          </section>
          <section className="profile-prose border-line max-lg:border-t max-lg:pt-6 lg:border-l lg:pl-10">
            <h2 className="stat m-0 pb-3 text-mute">portrait</h2>
            {portrait.map((paragraph, i) => (
              <p
                key={i}
                className={`mt-0 mb-4 leading-[1.65] ${i === 0 ? "text-[1.05rem] text-ink" : "text-ink2"}`}
              >
                {paragraph}
              </p>
            ))}
          </section>
        </div>

        {run.isError ? (
          <div className="delete-error" role="alert">
            synthesis failed: {String(run.error)}
          </div>
        ) : null}
      </div>
      {confirmDialog}
    </div>
  );
}
