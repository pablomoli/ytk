import { createRootRoute, Outlet } from "@tanstack/react-router";
import { ChromeProvider, useChromeVisible } from "../lib/chrome";
import { TooltipProvider } from "../components/ui/tooltip";
import { HubNav } from "../components/HubNav";

export const Route = createRootRoute({
  component: RootShell,
});

function RootShell() {
  return (
    <TooltipProvider>
      <ChromeProvider>
        <RootLayout />
      </ChromeProvider>
    </TooltipProvider>
  );
}

function RootLayout() {
  const chrome = useChromeVisible();
  return (
    <div className="hub-shell">
      {chrome ? (
        <header className="hub-nav px-2 py-1 sm:px-4">
          <HubNav />
        </header>
      ) : null}
      <main id="main-content" tabIndex={-1} className="hub-outlet">
        <Outlet />
      </main>
    </div>
  );
}
