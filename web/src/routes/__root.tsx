import { createRootRoute, Link, Outlet } from "@tanstack/react-router";
import { createContext, useState } from "react";

// The single header bar exposes a right-aligned slot; each route portals its
// page controls into it so there is exactly one header row on every page.
export const HubControlsContext = createContext<HTMLElement | null>(null);

export const Route = createRootRoute({
  component: RootLayout,
});

/* The shell is a plain top-to-bottom flex column: the nav is a static row that
   takes its own space, and .hub-outlet gets whatever is left and owns the
   scroll. Nothing below the nav has to know how tall the nav is, which is the
   point — the nav's eleven links re-wrap at widths that line up with no
   breakpoint, so its height is not a constant any stylesheet could name (#134). */
function RootLayout() {
  const [slot, setSlot] = useState<HTMLElement | null>(null);

  return (
    <HubControlsContext.Provider value={slot}>
      <div className="hub-shell">
        <header className="hub-nav">
          <nav className="hub-nav-links" aria-label="Hub navigation">
            <Link to="/" activeProps={{ className: "active" }}>
              fresh
            </Link>
            <Link to="/library" activeProps={{ className: "active" }}>
              library
            </Link>
            <Link to="/inbox" activeProps={{ className: "active" }}>
              inbox
            </Link>
            <Link to="/tags" activeProps={{ className: "active" }}>
              tags
            </Link>
            <Link to="/channels" activeProps={{ className: "active" }}>
              creators
            </Link>
            <Link to="/recs" activeProps={{ className: "active" }}>
              recs
            </Link>
            <Link to="/map" activeProps={{ className: "active" }}>
              map
            </Link>
            <Link to="/grove" activeProps={{ className: "active" }}>
              grove
            </Link>
            <Link to="/growth" activeProps={{ className: "active" }}>
              growth
            </Link>
            <Link to="/profile" activeProps={{ className: "active" }}>
              profile
            </Link>
            <Link to="/settings" activeProps={{ className: "active" }}>
              settings
            </Link>
          </nav>
          <div className="hub-controls" ref={setSlot} />
        </header>
        <main className="hub-outlet">
          <Outlet />
        </main>
      </div>
    </HubControlsContext.Provider>
  );
}
