import { expect, test, vi } from "vitest";
import { addUrls } from "./mutations";

test("addUrls posts urls", async () => {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify({ added: 1 }), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  await addUrls(["https://x"]);
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/queue/add",
    expect.objectContaining({ method: "POST" }),
  );
});
