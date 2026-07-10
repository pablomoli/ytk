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
        <a href="/tags">tags</a>
        <a href="/map">map</a>
        <a href="/settings">settings</a>
      </nav>
      <Outlet />
    </>
  );
}
