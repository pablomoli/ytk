import { expect, test } from "vitest";
import { editableProposals, mappingFromProposals } from "./tagMerge";

test("derives mappings only for accepted, included variants", () => {
  const groups = editableProposals([
    { canonical: "design", variants: ["ux", "ui"], counts: {} },
    { canonical: "skip", variants: ["ignore"], counts: {} },
  ]);
  groups[0].excluded.add("ui");
  groups[1].accepted = false;

  expect(mappingFromProposals(groups)).toEqual({ ux: "design" });
});
