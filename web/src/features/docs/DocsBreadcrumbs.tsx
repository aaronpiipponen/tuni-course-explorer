/** Canonically labelled wiki breadcrumb chain. */
import { Fragment } from "react";
import { DOCS_PAGES, DOCS_SECTIONS, type DocsPageId } from "./registry";

export function DocsBreadcrumbs({ pageId }: { pageId: DocsPageId }) {
  if (pageId === "home")
    return <div className="docs-crumbs">{DOCS_PAGES.home.nav}</div>;
  const page = DOCS_PAGES[pageId];
  const chain: DocsPageId[] = [];
  for (
    let current: DocsPageId | null = pageId;
    current;
    current = DOCS_PAGES[current].parent
  )
    chain.unshift(current);
  const section = DOCS_SECTIONS.find(
    (candidate) => candidate.title === page.section,
  )!;
  const below = chain.slice(1);
  return (
    <div className="docs-crumbs">
      <a href="/docs#home">{DOCS_PAGES.home.nav}</a>
      <span>/</span>
      {below.length === 0 ? (
        section.title
      ) : (
        <a href={`/docs#${section.page}`}>{section.title}</a>
      )}
      {below.map((id) => (
        <Fragment key={id}>
          <span>/</span>
          {id === pageId ? (
            DOCS_PAGES[id].nav
          ) : (
            <a href={`/docs#${id}`}>{DOCS_PAGES[id].nav}</a>
          )}
        </Fragment>
      ))}
    </div>
  );
}
