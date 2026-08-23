import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vite-plus/test";
import { Button } from "./button";

test("defaults to a non-submitting button", () => {
  const onSubmit = vi.fn((event: React.FormEvent) => event.preventDefault());
  render(
    <form onSubmit={onSubmit}>
      <Button>save</Button>
    </form>,
  );

  fireEvent.click(screen.getByRole("button", { name: "save" }));

  expect(onSubmit).not.toHaveBeenCalled();
});

test("keeps a 44px minimum product target", () => {
  render(<Button>save</Button>);

  const target = screen.getByRole("button", { name: "save" }).getBoundingClientRect();
  expect(target.height).toBeGreaterThanOrEqual(44);
  expect(target.width).toBeGreaterThanOrEqual(44);
});
