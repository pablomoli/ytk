import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./client";

export type DocsSectionSummary = {
  id: string; // "30-coastlines"
  num: number;
  title: string;
  deck: string;
  images: string[]; // docs-media-relative, figure order; the cards page these
  hasVideo: boolean;
};

export type DocsManifest = {
  available: boolean;
  sections: DocsSectionSummary[];
};

export type DocsSectionFile = {
  name: string;
  kind: "image" | "video" | "data";
  size: number;
};

export type DocsSection = {
  id: string;
  readme: string;
  files: DocsSectionFile[];
};

export const mediaUrl = (rel: string) => `/docs-media/${rel}`;

export const useDocsManifest = () =>
  useQuery({ queryKey: ["docs"], queryFn: () => apiGet<DocsManifest>("/api/docs") });

export const useDocsSection = (id: string) =>
  useQuery({
    queryKey: ["docs", id],
    queryFn: () => apiGet<DocsSection>(`/api/docs/${id}`),
  });
