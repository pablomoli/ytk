import { useMemo } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useChannels, useSetChannelStatus } from "../api/channels";
import type { Channel, ChannelStatus } from "../api/channels";
import { HubControls } from "../components/HubControls";
import { Skeletons } from "../components/Skeletons";
import { EmptyState, ErrorState } from "../components/StateViews";
import "../styles.css";

export const Route = createFileRoute("/channels")({
  component: ChannelsPage,
});

const SOURCE_ORDER = ["youtube", "instagram", "tiktok", "reddit", "pinterest", "web"];

function ChannelsPage() {
  const q = useChannels();
  const setStatus = useSetChannelStatus();

  const bySource = useMemo(() => {
    const groups = new Map<string, Channel[]>();
    for (const c of q.data ?? []) {
      const list = groups.get(c.source) ?? [];
      list.push(c);
      groups.set(c.source, list);
    }
    return [...groups.entries()].sort(
      (a, b) => (SOURCE_ORDER.indexOf(a[0]) + 100) % 100 - (SOURCE_ORDER.indexOf(b[0]) + 100) % 100,
    );
  }, [q.data]);

  const total = q.data?.length ?? 0;
  const loved = q.data?.filter((c) => c.status === "loved").length ?? 0;

  const toggle = (c: Channel, target: Exclude<ChannelStatus, null>) => {
    const status: ChannelStatus = c.status === target ? null : target;
    setStatus.mutate({ key: c.key, status });
  };

  let body;
  if (q.isLoading) {
    body = <Skeletons count={8} />;
  } else if (q.isError) {
    body = <ErrorState error={q.error} />;
  } else if (total === 0) {
    body = <EmptyState label="no creators yet" />;
  } else {
    body = (
      <div className="channels">
        {bySource.map(([source, list]) => (
          <section key={source} className="channel-group">
            <h2 className="channel-group-head">
              {source} <span className="count">{list.length}</span>
            </h2>
            <ul className="channel-list">
              {list.map((c) => (
                <li key={c.key} className={`channel-row${c.status ? ` ${c.status}` : ""}`}>
                  <span className="channel-name" title={c.channel}>
                    {c.channel}
                  </span>
                  <span className="channel-count" title={`${c.count} notes`}>
                    {c.count}
                  </span>
                  <span className="channel-tags">
                    {c.top_tags.map((t) => (
                      <span key={t} className="chip">
                        {t}
                      </span>
                    ))}
                  </span>
                  <span className="channel-actions">
                    <button
                      className={`btn tiny${c.status === "loved" ? " on" : ""}`}
                      onClick={() => toggle(c, "loved")}
                      aria-pressed={c.status === "loved"}
                    >
                      love
                    </button>
                    <button
                      className={`btn tiny${c.status === "muted" ? " on" : ""}`}
                      onClick={() => toggle(c, "muted")}
                      aria-pressed={c.status === "muted"}
                    >
                      mute
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    );
  }

  return (
    <div id="channels-page" className="hub-page">
      <HubControls>
        <span className="count">
          {total} creators{loved ? ` · ${loved} loved` : ""}
        </span>
      </HubControls>
      <div className="hub-body">{body}</div>
    </div>
  );
}
