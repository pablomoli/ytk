import type { TagProposal } from "../api/tagMerge";

export type EditableTagProposal = TagProposal & { accepted: boolean; excluded: Set<string> };

export function editableProposals(proposals: TagProposal[]): EditableTagProposal[] {
  return proposals.map((proposal) => ({ ...proposal, accepted: true, excluded: new Set() }));
}

export function mappingFromProposals(groups: EditableTagProposal[]): Record<string, string> {
  const mapping: Record<string, string> = {};
  for (const group of groups) {
    if (!group.accepted) continue;
    for (const tag of group.variants) {
      if (!group.excluded.has(tag)) mapping[tag] = group.canonical;
    }
  }
  return mapping;
}
