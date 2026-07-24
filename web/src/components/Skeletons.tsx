/* Placeholders shaped like real card anatomy (thumb + title + meta) instead
   of bare gray slabs. Deterministic variant cycle: media cards at three
   thumb heights, every fourth card a text card (no thumb). */
const THUMBS = [150, 220, 110, 0, 180, 130];

export function Skeletons({ count = 12 }: { count?: number }) {
  return (
    <>
      {Array.from({ length: count }, (_, i) => {
        const thumb = THUMBS[i % THUMBS.length];
        return (
          <div key={i} className="skel card">
            {thumb ? (
              <div className="skel-thumb" style={{ height: thumb }} />
            ) : (
              <div className="skel-text" />
            )}
            <div className="skel-meta">
              <div className="skel-line" style={{ width: `${72 - (i % 3) * 14}%` }} />
              <div className="skel-line skel-line-dim" style={{ width: `${38 + (i % 2) * 10}%` }} />
            </div>
          </div>
        );
      })}
    </>
  );
}
