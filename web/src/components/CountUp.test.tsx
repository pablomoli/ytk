import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { CountUp } from "./CountUp";

test("renders the value", () => {
  render(<CountUp value={128} />);
  expect(screen.getByText("128")).toBeInTheDocument();
});
