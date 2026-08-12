import { createRootRoute, Link, Outlet } from "@tanstack/react-router";
import { ChromeProvider, useChromeVisible } from "../lib/chrome";

export const Route = createRootRoute({
  component: RootShell,
});

function RootShell() {
  return (
    <ChromeProvider>
      <RootLayout />
    </ChromeProvider>
  );
}

/* The shell is a plain top-to-bottom flex column: the nav is a static row that
   takes its own space, and .hub-outlet gets whatever is left and owns the
   scroll. Nothing below the nav has to know how tall the nav is, which is the
   point — the nav's thirteen links re-wrap at widths that line up with no
   breakpoint, so its height is not a constant any stylesheet could name (#134). */
function RootLayout() {
  const chrome = useChromeVisible();
  return (
    <div className="hub-shell">
      {chrome ? (
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
            <Link to="/orb" activeProps={{ className: "active" }}>
              orb
            </Link>
            <Link to="/galaxy" activeProps={{ className: "active" }}>
              galaxy
            </Link>
            <Link to="/garden" activeProps={{ className: "active" }}>
              garden
            </Link>
            <Link to="/growth" activeProps={{ className: "active" }}>
              growth
            </Link>
            <Link to="/profile" activeProps={{ className: "active" }}>
              profile
            </Link>
            <Link to="/docs" activeProps={{ className: "active" }}>
              docs
            </Link>
            <Link to="/settings" activeProps={{ className: "active" }}>
              settings
            </Link>
          </nav>
        </header>
      ) : null}
      <main className="hub-outlet">
        <Outlet />
      </main>
    </div>
  );
}
