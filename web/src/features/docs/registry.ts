/** One generated registry shared by every wiki consumer. */
import generated from "virtual:wiki";
import type { DocsPageId, DocsRegistry } from "./types";

const typedRegistry = generated as DocsRegistry;

/** Every generated page, indexed by its page id. */
export const DOCS_PAGES = typedRegistry.pages;
/** The configured sections, each with the page it opens on. */
export const DOCS_SECTIONS = typedRegistry.sections;
/** The page ids of every configured section in reading order. */
export const DOCS_ORDER = typedRegistry.order;
/** The popular page ids in configured order. */
export const DOCS_POPULAR = typedRegistry.popular;
export type {
  DocsHeading,
  DocsPage,
  DocsPageId,
  DocsRegistry,
  DocsSection,
} from "./types";

/** Return whether one string names a generated page id. */
export function isDocsPageId(value: string): value is DocsPageId {
  return Object.prototype.hasOwnProperty.call(DOCS_PAGES, value);
}

/** Return the previous and next page of one page in reading order, with home first. */
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

/** Return the parent chain of one page, from its direct parent upward. */
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
