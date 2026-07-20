import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useProfile, useRunProfile } from "../api/profile";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { HubControls } from "../components/HubControls";
import { ScrollReveal } from "../components/ScrollReveal";
import { sourceIcon } from "../components/icons";
import { ErrorState } from "../components/StateViews";
import "../styles.css";

export const Route = createFileRoute("/profile")({ component: ProfilePage });

function ProfilePage() {
  const profile = useProfile();
  const run = useRunProfile();
  const [confirmSynth, setConfirmSynth] = useState(false);

  if (profile.isLoading) return <div className="hub-page"><div className="hub-body">loading profile...</div></div>;

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
      onConfirm={() => { setConfirmSynth(false); run.mutate(); }}
    />
  ) : null;

  if (profile.isError) {
    return <div className="hub-page">{controls}<div className="hub-body">
      <ErrorState error={profile.error} />
      <p className="profile-meta">no snapshot yet — re-synthesize to build one.</p>
    </div>{confirmDialog}</div>;
  }

  const data = profile.data!;
  const maxWeight = Math.max(...data.themes.map((theme) => theme.weight), 0.0001);
  const portrait = data.claims?.length
    ? data.claims.map((claim) => claim.text)
    : data.profile_markdown.split(/\n\n+/).filter(Boolean);

  return (
    <div id="profile-page" className="hub-page">
      {controls}
      <div className="hub-body profile-body">
        <p className="profile-meta">
          {data.note_count} notes · {data.themes.length} themes · synthesized {data.generated_at.slice(0, 16).replace("T", " ")}
          {data.embedding_model ? ` · ${data.embedding_model.split("/").pop()}` : ""}
          {data.reanchored_from ? " · re-anchored across an encoder swap" : ""}
        </p>
        <section className="profile-themes">
          {data.themes.map((theme) => (
            <details key={theme.id} className="profile-theme">
              <summary>
                <span className="profile-theme-label">{theme.label}</span>
                <span
                  className="profile-theme-bar"
                  role="meter"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round((theme.weight / maxWeight) * 100)}
                  aria-label={`${theme.label} weight`}
                >
                  <span style={{ transform: `scaleX(${theme.weight / maxWeight})` }} />
                </span>
                <span className="profile-theme-share">
                  {Math.round(theme.weight * 100)}% · {theme.n_notes} notes
                  {theme.fresh_notes && theme.fresh_notes < theme.n_notes ? ` · ${theme.fresh_notes} recent` : ""}
                </span>
              </summary>
              <p>{theme.summary}</p>
              {theme.exemplars.length ? (
                <ul>
                  {theme.exemplars.map((exemplar) => (
                    <li key={exemplar.title} className="profile-exemplar">
                      {exemplar.source ? sourceIcon(exemplar.source) : null}
                      {exemplar.title}
                    </li>
                  ))}
                </ul>
              ) : null}
            </details>
          ))}
        </section>
        <section className="profile-prose">
          {portrait.map((paragraph, i) => <ScrollReveal key={i}>{paragraph}</ScrollReveal>)}
        </section>
        {run.isError ? <div className="delete-error" role="alert">synthesis failed: {String(run.error)}</div> : null}
      </div>
      {confirmDialog}
    </div>
  );
}
