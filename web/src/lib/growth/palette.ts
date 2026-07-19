const hex = (v: number) => Math.round(v).toString(16).padStart(2, '0')

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
  const sizes = new Array<number>(k).fill(0)
  for (const a of assignment) sizes[a]++
  return centroids
    .map((c, i) => ({ c, size: sizes[i] }))
    .sort((a, b) => b.size - a.size)
    .map(({ c }) => `#${hex(c[0])}${hex(c[1])}${hex(c[2])}`)
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
