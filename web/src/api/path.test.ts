import { describe, expect, it, vi } from "vitest";
import { decodePath, fetchPath } from "./path";

const wire = {
  a: { title: "A", url: "https://youtu.be/aaa", video_id: "aaa" },
  b: { title: "B", url: "https://youtu.be/bbb", video_id: "bbb" },
  angle_deg: 60.0,
  background: 0.259,
  stops: [
    {
      t: 0.5,
      support: 0.75,
      notes: [{ title: "Mid", url: "https://youtu.be/mid", video_id: "mid", weight: 0.75 }],
    },
  ],
};

describe("decodePath", () => {
  it("decodes the wire shape verbatim", () => {
    const data = decodePath(wire);
    expect(data.a.video_id).toBe("aaa");
    expect(data.angle_deg).toBe(60.0);
    expect(data.stops[0].notes[0].weight).toBe(0.75);
  });

  it("tolerates missing fields at every level", () => {
    const data = decodePath({ stops: [{ notes: [{}] }, {}] });
    expect(data.a).toEqual({ title: "", url: null, video_id: null });
    expect(data.background).toBe(0);
    expect(data.stops).toHaveLength(2);
    expect(data.stops[0].notes[0]).toEqual({ title: "", url: null, video_id: null, weight: 0 });
    expect(data.stops[1].notes).toEqual([]);
  });

  it("tolerates a non-object payload", () => {
    expect(decodePath(null).stops).toEqual([]);
    expect(decodePath("nope").stops).toEqual([]);
  });
});

describe("fetchPath", () => {
  it("encodes endpoints and clamps nothing client-side", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(wire), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const data = await fetchPath("a b", "https://youtu.be/bbb?x=1", 11, 2);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/path?a=a+b&b=https%3A%2F%2Fyoutu.be%2Fbbb%3Fx%3D1&stops=11&k=2",
    );
    expect(data.stops[0].support).toBe(0.75);
    vi.unstubAllGlobals();
  });
});
