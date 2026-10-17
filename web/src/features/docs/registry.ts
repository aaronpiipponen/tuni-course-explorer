/** One generated registry shared by every wiki consumer. */
import generated from "virtual:wiki";
import type { DocsPageId, DocsRegistry } from "./types";

const typedRegistry = generated as DocsRegistry;

export const DOCS_REPOSITORY_URL = typedRegistry.repositoryUrl;
export const DOCS_PAGES = typedRegistry.pages;
export const DOCS_SECTIONS = typedRegistry.sections;
export const DOCS_ORDER = typedRegistry.order;
export const DOCS_POPULAR = typedRegistry.popular;
export type {
  DocsHeading,
  DocsPage,
  DocsPageId,
  DocsRegistry,
  DocsSection,
} from "./types";

export function isDocsPageId(value: string): value is DocsPageId {
  return Object.prototype.hasOwnProperty.call(DOCS_PAGES, value);
}

export function getDocsNeighbours(id: DocsPageId): {
  previous: DocsPageId | null;
  next: DocsPageId | null;
} {
  if (id === "home") return { previous: null, next: DOCS_ORDER[0] ?? null };
  const index = DOCS_ORDER.indexOf(id);
  return {
    previous: index === 0 ? "home" : DOCS_ORDER[index - 1],
    next: DOCS_ORDER[index + 1] ?? null,
  };
}

export function getDocsAncestors(id: DocsPageId): DocsPageId[] {
  const chain: DocsPageId[] = [];
  for (
    let current = DOCS_PAGES[id]?.parent;
    current;
    current = DOCS_PAGES[current].parent
  )
    chain.push(current);
  return chain;
}
