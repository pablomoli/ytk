import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/packet/")({ component: PacketIndex });

function PacketIndex() {
  return (
    <p className="mx-auto box-border w-full max-w-[1440px] px-4 pt-4 font-data text-[12.5px] tracking-[.04em] text-mute lowercase sm:px-7">
      click a packet, or press j
    </p>
  );
}
