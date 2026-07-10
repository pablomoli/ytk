import { createRootRoute, Link, Outlet } from "@tanstack/react-router";

export const Route = createRootRoute({
  component: () => (
    <>
      <nav>
        <Link to="/inbox">inbox</Link>
      </nav>
      <Outlet />
    </>
  ),
});
