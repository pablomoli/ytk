import { render } from "@testing-library/react";
import { expect, test } from "vitest";
import { PacketWaves } from "./PacketWaves";

test("the waves mount a canvas sized to their host and draw without throwing", async () => {
  const { getByTestId } = render(
    <PacketWaves
      packets={[
        {
          id: 1,
          title: "a",
          source: "youtube",
          station: { name: "owner", since: "2026-09-06T22:12:00Z", note: "", model: false },
          rounds: 0,
          calls: 0,
          tokens: 0,
        },
        {
          id: 2,
          title: "b",
          source: "youtube",
          station: { name: "student", since: "2026-09-06T22:12:00Z", note: "", model: true },
          rounds: 1,
          calls: 1,
          tokens: 900,
        },
      ]}
      className="relative block h-[150px] w-[600px]"
    />,
  );
  await new Promise((r) => setTimeout(r, 120));
  const canvas = getByTestId("waves").querySelector("canvas")!;
  expect(canvas.width).toBeGreaterThan(0);
  const px = canvas.getContext("2d")!.getImageData(0, 0, canvas.width, canvas.height).data;
  let lit = 0;
  for (let i = 0; i < px.length; i += 4) if (px[i]! > 40 || px[i + 1]! > 40) lit++;
  expect(lit).toBeGreaterThan(200);
});
