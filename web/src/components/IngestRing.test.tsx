import { render } from "@testing-library/react";
import { expect, test } from "vitest";
import { IngestRing } from "./IngestRing";

test("ring exposes progressbar semantics and fill fraction", () => {
  const { container } = render(<IngestRing done={3} total={8} running />);
  const ring = container.querySelector(".ingest-ring")!;
  expect(ring).toHaveAttribute("role", "progressbar");
  expect(ring).toHaveAttribute("aria-valuenow", "3");
  expect(ring).toHaveAttribute("aria-valuemax", "8");
  const fill = container.querySelector(".ingest-ring-fill") as SVGCircleElement;
  expect(fill.style.strokeDashoffset).not.toBe("");
});
