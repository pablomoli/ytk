const HEIGHTS = [220, 300, 180, 260, 340, 200]

export function Skeletons({ count = 12 }: { count?: number }) {
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="skel" style={{ height: HEIGHTS[i % HEIGHTS.length] }} />
      ))}
    </>
  )
}
