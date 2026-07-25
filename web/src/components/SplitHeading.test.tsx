import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { SplitHeading } from "./SplitHeading";

test("renders the heading text intact (animation is progressive enhancement)", () => {
  render(<SplitHeading>connections, not clusters</SplitHeading>);
  expect(screen.getByRole("heading")).toHaveTextContent("connections, not clusters");
});
