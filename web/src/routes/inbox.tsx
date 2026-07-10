import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/inbox")({
  validateSearch: (s: Record<string, unknown>): { source?: string } => ({
    source: typeof s.source === "string" ? s.source : undefined,
  }),
  component: InboxPage,
});

function InboxPage() {
  const { source } = Route.useSearch();
  return <div id="inbox-page">inbox route ok{source ? ` (filter: ${source})` : ""}</div>;
}
