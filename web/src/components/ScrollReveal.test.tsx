import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { ScrollReveal } from "./ScrollReveal";

test("renders paragraph text intact", () => {
  render(<ScrollReveal>the observatory is a private instrument</ScrollReveal>);
  expect(screen.getByText("the observatory is a private instrument")).toBeInTheDocument();
});
