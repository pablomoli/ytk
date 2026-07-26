import { createRootRoute, Link, Outlet } from "@tanstack/react-router";
import { createContext, useEffect, useState } from "react";
import { observeStickyTop } from "../lib/stickyTop";

// The single header bar exposes a right-aligned slot; each route portals its
// page controls into it so there is exactly one header row on every page.
export const HubControlsContext = createContext<HTMLElement | null>(null);

export const Route = createRootRoute({
  component: RootLayout,
});

function RootLayout() {
  const [slot, setSlot] = useState<HTMLElement | null>(null);

  // The nav wraps its links at widths that don't line up with any padding
  // breakpoint, so --sticky-top is measured rather than declared once here.
  useEffect(() => observeStickyTop(), []);

  return (
    <HubControlsContext.Provider value={slot}>
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
      <Outlet />
    </HubControlsContext.Provider>
  );
}
