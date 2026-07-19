export type Region = { x: number; y: number; w: number; h: number }

export function workbenchRegions(
  width: number,
  height: number,
): { stage: Region; mutations: Region[] } {
  const gutter = 8
  const stageW = Math.floor(width * 0.72)
  const colX = stageW + gutter
  const colW = width - colX
  const tileH = Math.floor((height - gutter * 3) / 4)
  const mutations = Array.from({ length: 4 }, (_, i) => ({
    x: colX,
    y: i * (tileH + gutter),
    w: colW,
    h: tileH,
  }))
  return { stage: { x: 0, y: 0, w: stageW, h: height }, mutations }
}
