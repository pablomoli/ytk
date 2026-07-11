import { createRootRoute, Link, Outlet } from "@tanstack/react-router";

export const Route = createRootRoute({
  component: RootLayout,
});

function RootLayout() {
  return (
    <>
      <nav className="hub-nav" aria-label="Hub navigation">
        <Link to="/" activeProps={{ className: "active" }}>
          fresh
        </Link>
        <Link to="/inbox" activeProps={{ className: "active" }}>
          inbox
        </Link>
        <Link to="/tags" activeProps={{ className: "active" }}>
          tags
        </Link>
        <Link to="/map" activeProps={{ className: "active" }}>
          map
        </Link>
        <Link to="/settings" activeProps={{ className: "active" }}>
          settings
        </Link>
      </nav>
      <Outlet />
    </>
  );
}
