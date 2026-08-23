export type MapCameraState = {
  scale: number;
  offset: [number, number];
  angle?: number;
  tilt?: number;
};

export const DEFAULT_MAP_CAMERA = {
  scale: 1,
  offset: [0, 0],
  angle: 0.5,
  tilt: 0.3,
} satisfies MapCameraState;

export function centerZoom(
  camera: Pick<MapCameraState, "scale" | "offset">,
  factor: number,
): Pick<MapCameraState, "scale" | "offset"> {
  const scale = Math.max(0.3, Math.min(12, camera.scale * factor));
  const ratio = scale / camera.scale;
  return {
    scale,
    offset: [camera.offset[0] * ratio, camera.offset[1] * ratio],
  };
}

export function resetCameraState(): MapCameraState {
  return { ...DEFAULT_MAP_CAMERA, offset: [...DEFAULT_MAP_CAMERA.offset] };
}
