import type { ReactNode } from "react";
import { useContext } from "react";
import { createPortal } from "react-dom";
import { HubControlsContext } from "../routes/__root";

// Render page controls into the single header bar's right-aligned slot.
export function HubControls({ children }: { children: ReactNode }) {
  const target = useContext(HubControlsContext);
  return target ? createPortal(children, target) : null;
}
