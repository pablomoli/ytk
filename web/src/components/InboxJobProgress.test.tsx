import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import type { JobStatus } from "../api/job";
import { InboxJobProgress } from "./InboxJobProgress";

const job = (overrides: Partial<JobStatus> = {}): JobStatus => ({
  running: true,
  total: 8,
  done: 3,
  current: "https://example.com/current",
  current_started: 1,
  queued: [],
  failures: [],
  annotated: 0,
  linked: [],
  ...overrides,
});

test("running progress counts remaining items down", () => {
  render(
    <InboxJobProgress
      job={job()}
      currentTitle="A long-running source"
      elapsed="2:17"
    />,
  );

  expect(screen.getByText("5 items remaining")).toBeInTheDocument();
  expect(screen.queryByText("3/8")).not.toBeInTheDocument();
  expect(screen.getByRole("progressbar")).toHaveAttribute(
    "aria-valuetext",
    "5 items remaining",
  );
});

test("remaining progress never becomes negative", () => {
  render(<InboxJobProgress job={job({ total: 2, done: 5 })} />);
  expect(screen.getByText("0 items remaining")).toBeInTheDocument();
  expect(screen.getByRole("progressbar")).toHaveAttribute(
    "aria-valuetext",
    "0 items remaining",
  );
});

test("the atomic live phrase excludes the elapsed timer", () => {
  render(
    <InboxJobProgress
      job={job()}
      currentTitle="A long-running source"
      elapsed="2:17"
    />,
  );

  const status = screen.getByRole("status");
  expect(status).toHaveAttribute("aria-atomic", "true");
  expect(status).toHaveTextContent("Ingest running. 5 items remaining.");
  expect(status).not.toHaveTextContent("2:17");
});

test("finished progress distinguishes success from failures", () => {
  const { rerender } = render(
    <InboxJobProgress job={job({ running: false, total: 3, done: 3 })} />,
  );
  expect(screen.getByText("3 items ingested")).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Ingest complete. 3 succeeded.");

  rerender(
    <InboxJobProgress
      job={job({
        running: false,
        total: 3,
        done: 3,
        failures: [{ url: "failed", error: "network error" }],
      })}
    />,
  );
  expect(screen.getByText("2 ingested")).toBeInTheDocument();
  expect(screen.getByText("1 failed")).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent(
    "Ingest complete with failures. 2 succeeded, 1 failed.",
  );
});

test("idle progress renders nothing", () => {
  const { container } = render(
    <InboxJobProgress job={job({ running: false, total: 0, done: 0 })} />,
  );
  expect(container).toBeEmptyDOMElement();
});
