import { useEffect, useRef, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { HubControls } from "../components/HubControls";
import type { GrowthHandle, GrowthStatus } from "../lib/growth/scene";
import "./growth.css";

export const Route = createFileRoute("/growth")({ component: GrowthDemo });

const INITIAL_STATUS: GrowthStatus = {
  count: 0,
  phase: "resting",
  message: "preparing organism",
  progress: 0,
};

function GrowthDemo() {
  const canvas = useRef<HTMLCanvasElement>(null);
  const handle = useRef<GrowthHandle>(null);
  const [status, setStatus] = useState(INITIAL_STATUS);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    let alive = true;
    void import("../lib/growth/scene").then(({ mountGrowth }) => {
      if (!alive || !canvas.current) return;
      handle.current = mountGrowth(canvas.current, (next) => setStatus(next));
    });
    return () => {
      alive = false;
      handle.current?.destroy();
      handle.current = null;
    };
  }, []);

  const togglePause = () => {
    const next = !paused;
    setPaused(next);
    handle.current?.setPaused(next);
  };

  return (
    <main className="growth-page">
      <HubControls>
        <button className="fchip" onClick={() => handle.current?.add("related")}>
          + related note
        </button>
        <button className="fchip" onClick={() => handle.current?.add("novel")}>
          + novel note
        </button>
        <button className={`fchip${paused ? " on" : ""}`} onClick={togglePause}>
          {paused ? "resume" : "pause"}
        </button>
        <button
          className="fchip"
          onClick={() => {
            setPaused(false);
            handle.current?.reset();
          }}
        >
          reset
        </button>
        <span className="count">{status.count} new events</span>
      </HubControls>

      <canvas
        ref={canvas}
        className="growth-canvas"
        aria-label="Procedural concept-growth organism"
      />

      <section className="growth-title">
        <p>concept-growth study · shared shader / persistent state</p>
        <h1>ytk</h1>
      </section>

      <aside className="growth-status" aria-live="polite">
        <div className="growth-status-row">
          <i className={`growth-live ${status.phase}`} />
          <span>{status.phase}</span>
          <time>state {String(status.count).padStart(3, "0")}</time>
        </div>
        <p>{status.message}</p>
        <div className="growth-progress">
          <i style={{ transform: `scaleX(${status.phase === "growing" ? status.progress : 1})` }} />
        </div>
        <dl>
          <div>
            <dt>renderer</dt>
            <dd>three.js / webgl</dd>
          </div>
          <div>
            <dt>identity</dt>
            <dd>seed 18421</dd>
          </div>
          <div>
            <dt>memory</dt>
            <dd>rgba state texture</dd>
          </div>
          <div>
            <dt>update</dt>
            <dd>localized growth event</dd>
          </div>
        </dl>
      </aside>

      <p className="growth-instruction">
        add a related note to deepen the body · add a novel note to push the perimeter
      </p>
    </main>
  );
}
