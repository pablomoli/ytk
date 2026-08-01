import { PerspectiveCamera, Vector3 } from "three";
import { expect, test } from "vitest";
import { pickTile, tileScreenRect } from "./pick";

function camera(): PerspectiveCamera {
  const cam = new PerspectiveCamera(60, 800 / 600, 0.01, 10);
  cam.position.set(0, 0, 0);
  cam.lookAt(0, 0, -1);
  cam.updateMatrixWorld();
  return cam;
}

test("tileScreenRect projects a known quad to known pixels", () => {
  const rect = tileScreenRect(camera(), new Vector3(0, 0, -1), 0.1, 800, 600);
  // half=0.1 at distance 1, fov 60: half-height px = 0.1 / tan(30deg) * 300
  const expectHalf = (0.1 / Math.tan(Math.PI / 6)) * 300;
  expect(rect.width / 2).toBeCloseTo(expectHalf, 0);
  expect(rect.left + rect.width / 2).toBeCloseTo(400, 0);
  expect(rect.top + rect.height / 2).toBeCloseTo(300, 0);
});

test("pickTile hits the centered tile and misses empty space", () => {
  const centers = new Float32Array([0, 0, -1, 1, 0, 0]);
  expect(pickTile(0, 0, camera(), centers, 0.08)).toBe(0);
  // straight up at the sphere's pole: no tile there
  expect(pickTile(0, 0.99, camera(), centers, 0.08)).toBeNull();
});

test("pickTile prefers the nearer of stacked tiles", () => {
  // both tiles straight ahead; the one on the near hemisphere side wins
  const centers = new Float32Array([0, 0, -1, 0, 0, 1]);
  expect(pickTile(0, 0, camera(), centers, 0.08)).toBe(0);
});
