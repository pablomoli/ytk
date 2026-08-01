import { expect, test, vi } from "vitest";
import { fetchOrb } from "./orb";

test("fetchOrb hits /api/orb and returns the payload", async () => {
  const payload = {
    points: [{ p: "a.md", t: "a", c: "youtube", u: null, d: null, th: 0, thumb: null }],
    themes: ["ai-tools"],
    sphere: { radial: [[0, 0, 1]], haversine: null, lattice: [[0, 1, 0]],
              scores: {}, chosen: "radial" },
  };
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(payload), { status: 200 }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const data = await fetchOrb();
  expect(fetchMock).toHaveBeenCalledWith("/api/orb");
  expect(data.sphere.chosen).toBe("radial");
  expect(data.points[0].p).toBe("a.md");
  vi.unstubAllGlobals();
});
