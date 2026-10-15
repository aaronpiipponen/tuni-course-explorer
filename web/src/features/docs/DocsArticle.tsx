/** Page-specific article framing, sanitized source Markdown and navigation. */
import { DocsBreadcrumbs } from "./DocsBreadcrumbs";
import { DocsHome } from "./DocsHome";
import { DocsPageNavigation } from "./DocsPageNavigation";
import { DOCS_PAGES, type DocsPageId } from "./registry";

export function DocsArticle({ pageId }: { pageId: DocsPageId }) {
  const page = DOCS_PAGES[pageId];
  if (pageId === "home")
    return (
      <article key={pageId}>
        <DocsBreadcrumbs pageId={pageId} />
        <DocsHome />
        <DocsPageNavigation pageId={pageId} />
      </article>
    );
  return (
    <article key={pageId}>
      <DocsBreadcrumbs pageId={pageId} />
      <h1 id={page.titleId}>{page.title}</h1>
      <div className="docs-meta docs-meta-page">
        Last updated {page.updated} · {page.readingMinutes} min read
      </div>
      <div
        className="docs-markdown"
        dangerouslySetInnerHTML={{ __html: page.html }}
      />
      <DocsPageNavigation pageId={pageId} />
    </article>
  );
}
