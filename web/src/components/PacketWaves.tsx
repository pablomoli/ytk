import { useEffect, useRef } from "react";
import type { TrackPacket } from "../api/packet";
import { mountPacketWaves } from "../lib/packetWaves";

/* The waves under the track: seven phosphor channels, one per station. */
export function PacketWaves({
  packets,
  t,
  className,
}: {
  packets: TrackPacket[] | undefined;
  t?: string | undefined;
  className?: string;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mounted = useRef<ReturnType<typeof mountPacketWaves> | undefined>(undefined);
  useEffect(() => {
    if (!hostRef.current || !canvasRef.current) return;
    mounted.current = mountPacketWaves(hostRef.current, canvasRef.current);
    return () => {
      mounted.current?.dispose();
      mounted.current = undefined;
    };
  }, []);
  useEffect(() => {
    mounted.current?.setData(packets, t ? () => Date.parse(t) : () => Date.now());
  }, [packets, t]);
  return (
    <div ref={hostRef} className={className} data-testid="waves">
      <canvas ref={canvasRef} className="absolute inset-0 block h-full w-full" />
      <div className="pointer-events-none absolute inset-0 [background:repeating-linear-gradient(0deg,transparent_0_2px,rgba(0,0,0,.14)_2px_3px)]" />
      <div className="pointer-events-none absolute inset-0 [background:radial-gradient(ellipse_at_center,transparent_60%,rgba(0,0,0,.45)_100%)]" />
    </div>
  );
}
