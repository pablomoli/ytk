import type { CSSProperties } from "react";
import type { FaceName } from "../orbSearch";
import besleyItalic from "../../fonts/Besley-italic.woff2?url";
import besley from "../../fonts/Besley-normal.woff2?url";
import frauncesItalic from "../../fonts/Fraunces-italic.woff2?url";
import fraunces from "../../fonts/Fraunces-normal.woff2?url";
import fellItalic from "../../fonts/IMFellDWPica-italic.woff2?url";
import fell from "../../fonts/IMFellDWPica-normal.woff2?url";
import instrumentItalic from "../../fonts/InstrumentSerif-italic.woff2?url";
import instrument from "../../fonts/InstrumentSerif-normal.woff2?url";

// Candidate display faces for the orb's titles and controls; the reader's
// running text stays Newsreader. The winner moves to theme.css and this goes.
type Face = {
  family: string;
  files: [string, string] | null; // roman, italic; null is the hub's own face
  range: string; // the weights the files hold
  weight: number;
  scale: number; // against Newsreader at the same px: a narrow or small-bodied face is set larger
  track: string;
  vary: string;
};

export const FACES: Record<FaceName, Face> = {
  instrument: { family: "Instrument Serif", files: [instrument, instrumentItalic], range: "400", weight: 400, scale: 1.22, track: "0em", vary: "normal" },
  fraunces: { family: "Fraunces", files: [fraunces, frauncesItalic], range: "100 900", weight: 520, scale: 1, track: "-0.02em", vary: '"SOFT" 100, "WONK" 1' },
  besley: { family: "Besley", files: [besley, besleyItalic], range: "400 900", weight: 540, scale: 0.95, track: "-0.015em", vary: "normal" },
  fell: { family: "IM Fell DW Pica", files: [fell, fellItalic], range: "400", weight: 400, scale: 1.12, track: "0em", vary: "normal" },
  news: { family: "Newsreader", files: null, range: "400", weight: 400, scale: 1, track: "-0.01em", vary: "normal" },
};

export const faceStack = (name: FaceName) => `"${FACES[name].family}", "Newsreader", Georgia, serif`;

// the face as custom properties; --data carries it into buttons and inputs, which theme.css sets from that token
export const faceVars = (name: FaceName) =>
  ({
    "--face": faceStack(name),
    "--data": faceStack(name),
    "--face-w": FACES[name].weight,
    "--face-k": FACES[name].scale,
    "--face-track": FACES[name].track,
    "--face-vary": FACES[name].vary,
  }) as CSSProperties;

// resolves once the face can be drawn, on the page and into a canvas; a face that never arrives falls back
export async function loadFace(name: FaceName): Promise<void> {
  const f = FACES[name];
  if (f.files && ![...document.fonts].some((x) => x.family.replace(/"/g, "") === f.family)) {
    (["normal", "italic"] as const).forEach((style, k) => {
      document.fonts.add(new FontFace(f.family, `url(${f.files![k]}) format("woff2")`, { weight: f.range, style }));
    });
  }
  const drawn = Promise.all([
    document.fonts.load(`${f.weight} 16px "${f.family}"`),
    document.fonts.load(`italic ${f.weight} 16px "${f.family}"`),
  ]);
  await Promise.race([drawn.catch(() => undefined), new Promise((r) => window.setTimeout(r, 3000))]);
}
