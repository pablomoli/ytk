import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { HubControls } from "../components/HubControls";
import { SplitHeading } from "../components/SplitHeading";
import "./transit.css";

export const Route = createFileRoute("/transit")({ component: TransitDemo });

type RouteId = "ytk" | "epicmap";

type Station = {
  id: string;
  label: string;
  route: RouteId | "both";
  x: number;
  y: number;
  side: "above" | "below";
  kind: "note" | "memo" | "decision" | "interchange";
  detail: string;
  evidence: string;
};

const ROUTES = {
  ytk: { label: "ytk", color: "#5f8ee4", glow: "#5f8ee455" },
  epicmap: { label: "epicmap", color: "#d97945", glow: "#d9794555" },
} as const;

const STATIONS: Station[] = [
  {
    id: "capture",
    label: "capture rails",
    route: "ytk",
    x: 112,
    y: 222,
    side: "above",
    kind: "note",
    detail: "A project station: one real note on the ytk route.",
    evidence: "memory · purpose.md · updated 4d ago",
  },
  {
    id: "profile",
    label: "interest model",
    route: "ytk",
    x: 278,
    y: 222,
    side: "below",
    kind: "decision",
    detail: "A stronger station because it is a durable decision, not merely a passing mention.",
    evidence: "decision · profile-v2.md · signal 0.91",
  },
  {
    id: "grove",
    label: "grove experiments",
    route: "ytk",
    x: 442,
    y: 222,
    side: "above",
    kind: "note",
    detail: "Related ytk work stays on the same line, ordered as a readable conceptual journey.",
    evidence: "memory · grove.md · 41 linked notes",
  },
  {
    id: "map",
    label: "brain map",
    route: "ytk",
    x: 574,
    y: 274,
    side: "below",
    kind: "note",
    detail:
      "The route bends when the project changes direction; distance is editorial, not a literal metric.",
    evidence: "feature · map-v3.md · active",
  },
  {
    id: "parcels",
    label: "parcel records",
    route: "epicmap",
    x: 112,
    y: 542,
    side: "above",
    kind: "note",
    detail: "Epicmap has its own authored route and persistent color.",
    evidence: "memory · parcels.md · 28 linked notes",
  },
  {
    id: "layers",
    label: "county layers",
    route: "epicmap",
    x: 282,
    y: 542,
    side: "below",
    kind: "note",
    detail: "Nearby stations are facets of the same project, not fake top-level clusters.",
    evidence: "memory · gis-layers.md · updated 9d ago",
  },
  {
    id: "field",
    label: "field operations",
    route: "epicmap",
    x: 450,
    y: 542,
    side: "above",
    kind: "memo",
    detail:
      "A voice memo can be a station too. Its source type changes the center mark, not the route.",
    evidence: "memo · 02:14 · thought attached",
  },
  {
    id: "crew",
    label: "crew navigation",
    route: "epicmap",
    x: 570,
    y: 470,
    side: "below",
    kind: "note",
    detail: "The line approaches a shared idea without merging into the other project.",
    evidence: "memory · field-ux.md · signal 0.78",
  },
  {
    id: "zoom",
    label: "semantic zoom",
    route: "both",
    x: 682,
    y: 360,
    side: "above",
    kind: "interchange",
    detail:
      "This is the important part: an interchange where two authored projects genuinely share an idea.",
    evidence: "3 supporting notes · confirmed connection",
  },
  {
    id: "hierarchy",
    label: "progressive detail",
    route: "ytk",
    x: 838,
    y: 360,
    side: "below",
    kind: "decision",
    detail: "After the interchange, each project continues along its own direction.",
    evidence: "decision · map hierarchy · accepted",
  },
  {
    id: "discovery",
    label: "public discovery",
    route: "ytk",
    x: 1018,
    y: 360,
    side: "above",
    kind: "note",
    detail: "A terminal station can represent the current edge of a project.",
    evidence: "question · showcase direction · open",
  },
  {
    id: "status",
    label: "job status",
    route: "epicmap",
    x: 824,
    y: 278,
    side: "below",
    kind: "note",
    detail: "Crossing at semantic zoom does not collapse the projects into one inferred theme.",
    evidence: "memory · status-tracking.md · 17 linked notes",
  },
  {
    id: "mobile",
    label: "mobile field ux",
    route: "epicmap",
    x: 1018,
    y: 174,
    side: "above",
    kind: "decision",
    detail: "The orange line remains epicmap even when its concepts resemble ytk work.",
    evidence: "decision · mobile-navigation.md · active",
  },
];

function TransitDemo() {
  const [selectedId, setSelectedId] = useState("zoom");
  const [focus, setFocus] = useState<RouteId | "all">("all");
  const selected = STATIONS.find((station) => station.id === selectedId) ?? STATIONS[8];
  const isVisible = (route: Station["route"]) =>
    focus === "all" || route === focus || route === "both";

  return (
    <main className="transit-page">
      <HubControls>
        <button className={`fchip${focus === "all" ? " on" : ""}`} onClick={() => setFocus("all")}>
          all routes
        </button>
        <button className={`fchip${focus === "ytk" ? " on" : ""}`} onClick={() => setFocus("ytk")}>
          ytk
        </button>
        <button
          className={`fchip${focus === "epicmap" ? " on" : ""}`}
          onClick={() => setFocus("epicmap")}
        >
          epicmap
        </button>
        <span className="count">concept demo</span>
      </HubControls>

      <section className="transit-intro">
        <p className="transit-kicker">knowledge transit · concept 01</p>
        <SplitHeading>connections, not clusters</SplitHeading>
        <p>Projects are lines. Memories are stations. Shared ideas become interchanges.</p>
      </section>

      <div className="transit-layout">
        <section className="transit-map-wrap" aria-label="Knowledge transit map demo">
          <div className="transit-legend" aria-hidden="true">
            <span>
              <i style={{ background: ROUTES.ytk.color }} />
              ytk
            </span>
            <span>
              <i style={{ background: ROUTES.epicmap.color }} />
              epicmap
            </span>
          </div>
          <svg
            className="transit-map"
            viewBox="0 0 1120 650"
            role="img"
            aria-labelledby="transit-title transit-desc"
          >
            <title id="transit-title">Two project routes meeting at semantic zoom</title>
            <desc id="transit-desc">
              A blue ytk line and orange epicmap line connect at one interchange, with clickable
              memory stations along each route.
            </desc>
            <defs>
              <filter id="soft-glow" x="-30%" y="-30%" width="160%" height="160%">
                <feGaussianBlur stdDeviation="6" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
              <pattern id="grid" width="38" height="38" patternUnits="userSpaceOnUse">
                <path
                  d="M 38 0 L 0 0 0 38"
                  fill="none"
                  stroke="#ffffff"
                  strokeOpacity=".022"
                  strokeWidth="1"
                />
              </pattern>
            </defs>
            <rect width="1120" height="650" fill="url(#grid)" />

            <g className={`transit-route${focus === "epicmap" ? " muted" : ""}`}>
              <path
                className="route-bed"
                d="M112 222 H442 C515 222 540 254 574 274 L682 360 H1018"
              />
              <path
                className="route-glow"
                stroke={ROUTES.ytk.glow}
                d="M112 222 H442 C515 222 540 254 574 274 L682 360 H1018"
              />
              <path
                className="route-line"
                stroke={ROUTES.ytk.color}
                d="M112 222 H442 C515 222 540 254 574 274 L682 360 H1018"
              />
            </g>
            <g className={`transit-route${focus === "ytk" ? " muted" : ""}`}>
              <path
                className="route-bed"
                d="M112 542 H450 C505 542 539 508 570 470 L682 360 C737 324 774 305 824 278 L1018 174"
              />
              <path
                className="route-glow"
                stroke={ROUTES.epicmap.glow}
                d="M112 542 H450 C505 542 539 508 570 470 L682 360 C737 324 774 305 824 278 L1018 174"
              />
              <path
                className="route-line"
                stroke={ROUTES.epicmap.color}
                d="M112 542 H450 C505 542 539 508 570 470 L682 360 C737 324 774 305 824 278 L1018 174"
              />
            </g>

            {STATIONS.map((station) => {
              const chosen = station.id === selectedId;
              const color = station.route === "both" ? "#f0eee7" : ROUTES[station.route].color;
              return (
                <g
                  key={station.id}
                  className={`transit-station${chosen ? " selected" : ""}${isVisible(station.route) ? "" : " muted"}`}
                  role="button"
                  tabIndex={0}
                  aria-label={`${station.label}, ${station.route === "both" ? "interchange" : `${station.route} station`}`}
                  onClick={() => setSelectedId(station.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") setSelectedId(station.id);
                  }}
                  transform={`translate(${station.x} ${station.y})`}
                >
                  {station.kind === "interchange" ? (
                    <>
                      <circle className="interchange-halo" r="28" />
                      <circle
                        className="station-ring"
                        r="15"
                        fill="#0a0a0c"
                        stroke={ROUTES.ytk.color}
                        strokeWidth="7"
                      />
                      <path
                        d="M-11 11 L11 -11"
                        stroke={ROUTES.epicmap.color}
                        strokeWidth="7"
                        strokeLinecap="round"
                      />
                      <circle className="station-core" r="5" fill="#f0eee7" />
                    </>
                  ) : (
                    <>
                      <circle className="station-hit" r="20" />
                      <circle
                        className="station-ring"
                        r={chosen ? 10 : 8}
                        fill="#0a0a0c"
                        stroke={color}
                        strokeWidth={chosen ? 5 : 4}
                      />
                      {station.kind === "decision" ? <circle r="2.5" fill={color} /> : null}
                      {station.kind === "memo" ? (
                        <path
                          d="M-2 -4 V4 M2 -3 V3"
                          stroke={color}
                          strokeWidth="1.5"
                          strokeLinecap="round"
                        />
                      ) : null}
                    </>
                  )}
                  <text
                    className={`station-label ${station.side}`}
                    x="0"
                    y={station.side === "above" ? -23 : 30}
                    textAnchor="middle"
                  >
                    {station.label}
                  </text>
                  <text
                    className={`station-type ${station.side}`}
                    x="0"
                    y={station.side === "above" ? -39 : 46}
                    textAnchor="middle"
                  >
                    {station.kind}
                  </text>
                </g>
              );
            })}
          </svg>
          <p className="transit-map-hint">select a station · filter a project above</p>
        </section>

        <aside className="transit-detail" key={selected.id}>
          <div className="transit-detail-route">
            {selected.route === "both" ? (
              <span className="double-dot">
                <i style={{ background: ROUTES.ytk.color }} />
                <i style={{ background: ROUTES.epicmap.color }} />
              </span>
            ) : (
              <i style={{ background: ROUTES[selected.route].color }} />
            )}
            {selected.route === "both" ? "interchange" : selected.route}
          </div>
          <p className="transit-detail-type">{selected.kind}</p>
          <h2>{selected.label}</h2>
          <p className="transit-detail-copy">{selected.detail}</p>
          <div className="transit-evidence">
            <span>grounded by</span>
            <p>{selected.evidence}</p>
          </div>
          {selected.route === "both" ? (
            <div className="transit-why">
              <span>why these routes meet</span>
              <p>
                Both projects use progressive disclosure: show the territory first, reveal
                operational detail as the viewer moves closer.
              </p>
              <button type="button">
                open 3 supporting notes <span>↗</span>
              </button>
            </div>
          ) : (
            <button className="transit-open" type="button">
              open source note <span>↗</span>
            </button>
          )}
        </aside>
      </div>
    </main>
  );
}
