import { createRootRoute, Outlet } from "@tanstack/react-router";

// The inbox page renders its own header; the root just hosts the routed page.
// (A cross-page nav bar returns once more than one page is migrated.)
export const Route = createRootRoute({
  component: () => <Outlet />,
});
