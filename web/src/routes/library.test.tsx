import { render } from "@testing-library/react";
import { expect, test, vi } from "vitest";

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({ options, useSearch: () => ({}) }),
  useNavigate: () => vi.fn(),
}));
vi.mock("../components/HubControls", () => ({
  HubControls: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock("../components/RecapPanel", () => ({
  RecapPanel: () => <div data-testid="recap" />,
}));
const emptyPage = { isLoading: false, isError: false, data: { total: 0, items: [] } };
vi.mock("../api/library", () => ({
  useLibrary: () => emptyPage,
}));
vi.mock("../api/fresh", () => ({
  useDeleteNote: () => ({ mutate: vi.fn(), isError: false }),
  useNote: () => ({ isLoading: false, isError: false }),
  useSimilarNotes: () => ({ isLoading: false, isError: false }),
}));

import { Route } from "./library";

test("library opens with the recency-first recap section", () => {
  const Page = (Route as unknown as { options: { component: React.ComponentType } }).options
    .component;
  const { getByTestId } = render(<Page />);
  expect(getByTestId("recap")).toBeInTheDocument();
});
