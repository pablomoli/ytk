const SPANS = [22, 30, 18, 26, 34, 20]

export function Skeletons({ count = 12 }: { count?: number }) {
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="skel" style={{ gridRowEnd: `span ${SPANS[i % SPANS.length]}` }} />
      ))}
    </>
  )
}
