const hex = (v: number) => Math.round(v).toString(16).padStart(2, '0')

// Render roles need a guaranteed value structure — covers are often dark-mode
// screenshots whose raw clusters are uniformly murky. Hue and saturation come
// from the content; lightness is anchored per role slot.
const ROLE_LIGHTNESS = [0.09, 0.34, 0.56, 0.68, 0.87]

function anchorLightness(rgb: [number, number, number], target: number): [number, number, number] {
  const [r, g, b] = rgb.map((v) => v / 255)
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const l = (max + min) / 2
  const d = max - min
  let h = 0
  const s = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1))
  if (d !== 0) {
    if (max === r) h = ((g - b) / d) % 6
    else if (max === g) h = (b - r) / d + 2
    else h = (r - g) / d + 4
    h *= 60
    if (h < 0) h += 360
  }
  const c = (1 - Math.abs(2 * target - 1)) * Math.min(s, 0.85)
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1))
  const m = target - c / 2
  let rgb1: [number, number, number]
  if (h < 60) rgb1 = [c, x, 0]
  else if (h < 120) rgb1 = [x, c, 0]
  else if (h < 180) rgb1 = [0, c, x]
  else if (h < 240) rgb1 = [0, x, c]
  else if (h < 300) rgb1 = [x, 0, c]
  else rgb1 = [c, 0, x]
  return [(rgb1[0] + m) * 255, (rgb1[1] + m) * 255, (rgb1[2] + m) * 255]
}

export function kmeansPalette(pixels: Uint8ClampedArray, k = 5): string[] {
  const points: Array<[number, number, number]> = []
  for (let i = 0; i + 3 < pixels.length; i += 16) {
    if (pixels[i + 3] < 128) continue
    points.push([pixels[i], pixels[i + 1], pixels[i + 2]])
  }
  if (!points.length) points.push([0, 0, 0])
  // Deterministic init: evenly spaced samples.
  let centroids = Array.from({ length: k }, (_, i) => {
    const p = points[Math.floor((i * points.length) / k)]
    return [p[0], p[1], p[2]] as [number, number, number]
  })
  const assignment = new Array<number>(points.length).fill(0)
  for (let iter = 0; iter < 10; iter++) {
    for (let p = 0; p < points.length; p++) {
      let best = 0
      let bestDist = Infinity
      for (let c = 0; c < k; c++) {
        const dr = points[p][0] - centroids[c][0]
        const dg = points[p][1] - centroids[c][1]
        const db = points[p][2] - centroids[c][2]
        const d = dr * dr + dg * dg + db * db
        if (d < bestDist) {
          bestDist = d
          best = c
        }
      }
      assignment[p] = best
    }
    const sums = Array.from({ length: k }, () => [0, 0, 0, 0])
    for (let p = 0; p < points.length; p++) {
      const s = sums[assignment[p]]
      s[0] += points[p][0]
      s[1] += points[p][1]
      s[2] += points[p][2]
      s[3]++
    }
    centroids = sums.map((s, c) =>
      s[3] ? ([s[0] / s[3], s[1] / s[3], s[2] / s[3]] as [number, number, number]) : centroids[c],
    )
  }
  // Luminance-ascending so palette indices keep their semantic render roles:
  // [0] deep field, [1] mid tissue, [2] high tissue, [3] vessel, [4] membrane.
  return centroids
    .map((c) => ({ c, lum: 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2] }))
    .sort((a, b) => a.lum - b.lum)
    .map(({ c }, i) => anchorLightness(c, ROLE_LIGHTNESS[Math.min(i, ROLE_LIGHTNESS.length - 1)]))
    .map((c) => `#${hex(c[0])}${hex(c[1])}${hex(c[2])}`)
}

export async function paletteFromCovers(urls: string[]): Promise<string[] | null> {
  const pixels: number[] = []
  for (const url of urls.slice(0, 3)) {
    try {
      const img = new Image()
      img.decoding = 'async'
      img.src = url
      await img.decode()
      const canvas = document.createElement('canvas')
      canvas.width = 48
      canvas.height = 48
      const ctx = canvas.getContext('2d')
      if (!ctx) continue
      ctx.drawImage(img, 0, 0, 48, 48)
      pixels.push(...ctx.getImageData(0, 0, 48, 48).data)
    } catch {
      continue
    }
  }
  if (!pixels.length) return null
  return kmeansPalette(new Uint8ClampedArray(pixels), 5)
}
