import { useEffect, useMemo, useState } from "react";
import { CheckIcon, XIcon } from "@phosphor-icons/react";
import { createFileRoute } from "@tanstack/react-router";
import { useApplyTagMerges, useProposeTagMerges, useTagMergeStatus } from "../api/tagMerge";
import type { EditableTagProposal } from "../lib/tagMerge";
import { editableProposals, mappingFromProposals } from "../lib/tagMerge";
import { useHoverDecode } from "../lib/useHoverDecode";
import { HubControls } from "../components/HubControls";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Button } from "../components/ui/button";
import { IconButton } from "../components/ui/icon-button";
import "../styles.css";

export const Route = createFileRoute("/tags")({ component: TagsPage });

function TagsPage() {
  const status = useTagMergeStatus();
  const propose = useProposeTagMerges();
  const apply = useApplyTagMerges();
  const decode = useHoverDecode();
  const [groups, setGroups] = useState<EditableTagProposal[]>([]);
  const [message, setMessage] = useState("");
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    if (status.data?.state === "done") {
      const proposals = status.data.proposals;
      setGroups((current) => (current.length ? current : editableProposals(proposals)));
    }
  }, [status.data]);

  const mapping = useMemo(() => mappingFromProposals(groups), [groups]);
  const retired = Object.keys(mapping).length;

  const updateGroup = (
    index: number,
    update: (group: EditableTagProposal) => EditableTagProposal,
  ) => {
    setGroups((current) =>
      current.map((group, groupIndex) => (groupIndex === index ? update(group) : group)),
    );
  };

  const makeCanonical = (index: number, tag: string) =>
    updateGroup(index, (group) => ({
      ...group,
      canonical: tag,
      variants: [group.canonical, ...group.variants].filter((variant) => variant !== tag),
      excluded: new Set([...group.excluded].filter((variant) => variant !== tag)),
    }));

  const toggleExcluded = (index: number, tag: string) =>
    updateGroup(index, (group) => {
      const excluded = new Set(group.excluded);
      if (excluded.has(tag)) excluded.delete(tag);
      else excluded.add(tag);
      return { ...group, excluded };
    });

  const start = () => {
    setMessage("");
    setGroups([]);
    propose.mutate(undefined, {
      onError: (error) => setMessage(`failed to start: ${String(error)}`),
    });
  };

  const submit = () => {
    setConfirming(false);
    apply.mutate(mapping, {
      onSuccess: (result) => {
        setGroups([]);
        setMessage(
          `applied: ${result.aliases} aliases saved, ${result.notes} notes rewritten, ${result.videos} index entries updated`,
        );
      },
      onError: (error) => setMessage(`apply failed: ${String(error)}`),
    });
  };

  const stateMessage =
    status.data?.state === "running"
      ? "Finding duplicate tag vocabulary with the configured model."
      : status.data?.state === "error"
        ? status.data.detail || "proposal generation failed"
        : status.data?.state === "done" && !status.data.proposals.length
          ? "No merge candidates found. The vocabulary is clean."
          : status.data?.state === "idle"
            ? "No cleanup is running."
            : message;
  const statusRole = status.data?.state === "error" ? "alert" : "status";

  return (
    <div className="tags-page min-h-full bg-bg0 text-ink">
      <HubControls>
        <span className="count">{groups.length ? `${groups.length} groups` : ""}</span>
      </HubControls>
      <main className="tags-main mx-auto flex max-w-3xl flex-col gap-6 px-4 py-8">
        <header className="max-w-2xl">
          <p className="mb-2 font-data text-xs tracking-[0.12em] text-mute uppercase">
            Maintenance
          </p>
          <h1 className="m-0 font-serif text-3xl font-normal text-ink">Tag cleanup</h1>
          <p className="mt-3 text-base leading-7 text-ink2">
            Periodic vocabulary maintenance for merging duplicate tags. Review every suggestion
            before anything changes.
          </p>
        </header>
        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            onClick={start}
            disabled={propose.isPending || status.data?.state === "running"}
          >
            Find merge candidates
          </Button>
          <span
            role={statusRole}
            aria-live={statusRole === "status" ? "polite" : undefined}
            className={statusRole === "alert" ? "text-live" : "text-sm text-mute"}
          >
            {stateMessage}
          </span>
        </div>
        {groups.length ? (
          <p className="m-0 text-sm leading-6 text-mute">
            Choose the canonical tag, exclude variants that should stay independent, then merge or
            skip each group.
          </p>
        ) : null}
        <div className="flex flex-col gap-4">
          {groups.map((group, index) => (
            <section
              className={`rounded-card border p-4 ${group.accepted ? "border-line bg-bg1" : "border-line/60 bg-bg1/60 opacity-70"}`}
              key={`${group.canonical}-${index}`}
              aria-label={`Merge group ${index + 1}`}
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="flex flex-1 flex-wrap gap-2">
                  {[group.canonical, ...group.variants].map((tag) => {
                    const canonical = tag === group.canonical;
                    const excluded = group.excluded.has(tag);
                    return (
                      <span
                        className={`inline-flex items-center gap-1 rounded-lg border p-1 ${excluded ? "border-line/60 opacity-50" : "border-line"}`}
                        key={tag}
                      >
                        <Button
                          variant={canonical ? "default" : "secondary"}
                          size="sm"
                          type="button"
                          aria-pressed={canonical}
                          aria-label={canonical ? `${tag}, canonical` : `Make ${tag} canonical`}
                          disabled={canonical}
                          onClick={() => (canonical ? undefined : makeCanonical(index, tag))}
                        >
                          <span className="tag-name" onMouseEnter={decode.onMouseEnter}>
                            {tag}
                          </span>
                          <span className={canonical ? "text-bg0/70" : "text-mute"}>
                            {group.counts[tag] ?? ""}
                          </span>
                          {canonical ? (
                            <>
                              <CheckIcon aria-hidden="true" className="size-4" />
                              <span className="text-xs">canonical</span>
                            </>
                          ) : null}
                        </Button>
                        {!canonical ? (
                          <IconButton
                            label={
                              excluded
                                ? `Include ${tag} in this merge`
                                : `Exclude ${tag} from this merge`
                            }
                            aria-pressed={excluded}
                            onClick={() => toggleExcluded(index, tag)}
                          >
                            <XIcon />
                          </IconButton>
                        ) : null}
                      </span>
                    );
                  })}
                </div>
                <div className="flex gap-2" role="group" aria-label={`Decision for group ${index + 1}`}>
                  <Button
                    variant={group.accepted ? "default" : "secondary"}
                    type="button"
                    aria-label="Merge this group"
                    aria-pressed={group.accepted}
                    onClick={() =>
                      updateGroup(index, (current) => ({ ...current, accepted: true }))
                    }
                  >
                    Merge
                  </Button>
                  <Button
                    variant={group.accepted ? "secondary" : "default"}
                    type="button"
                    aria-label="Skip this group"
                    aria-pressed={!group.accepted}
                    onClick={() =>
                      updateGroup(index, (current) => ({ ...current, accepted: false }))
                    }
                  >
                    Skip
                  </Button>
                </div>
              </div>
            </section>
          ))}
        </div>
      </main>
      {groups.length ? (
        <div className="tag-apply-bar sticky bottom-0 flex flex-wrap items-center gap-3 border-t border-line bg-bg1 px-4 py-3">
          <Button
            type="button"
            onClick={() => setConfirming(true)}
            disabled={!retired || apply.isPending}
          >
            Apply selected merges
          </Button>
          <span className="text-sm text-mute">
            {retired
              ? `${retired} tags will become ${new Set(Object.values(mapping)).size} canonical tags`
              : "No merges selected"}
          </span>
        </div>
      ) : null}
      {confirming ? (
        <ConfirmDialog
          message={`Apply ${retired} tag aliases? This rewrites matching notes and updates the permanent alias map.`}
          confirmLabel="Apply merges"
          onConfirm={submit}
          onCancel={() => setConfirming(false)}
        />
      ) : null}
    </div>
  );
}
