/** Fixed-width previous and next links following the shared registry order. */
import { DOCS_PAGES, getDocsNeighbours, type DocsPageId } from "./registry";

export function DocsPageNavigation({ pageId }: { pageId: DocsPageId }) {
  const { previous, next } = getDocsNeighbours(pageId);
  const link = (id: DocsPageId, direction: "previous" | "next") => (
    <a className={direction} href={`/docs#${id}`}>
      <small>{direction === "previous" ? "Previous" : "Next"}</small>
      <b>
        {direction === "previous" ? "← " : ""}
        {DOCS_PAGES[id].nav}
        {direction === "next" ? " →" : ""}
      </b>
    </a>
  );
  return (
    <div className="docs-pn">
      {previous ? link(previous, "previous") : <span />}
      {next ? link(next, "next") : <span />}
    </div>
  );
}
