/** Page-specific article framing, sanitized source Markdown and navigation. */
import { DocsBreadcrumbs } from "./DocsBreadcrumbs";
import { DocsPageTools } from "./DocsPageTools";
import { DocsHome } from "./DocsHome";
import { DocsPageNavigation } from "./DocsPageNavigation";
import { DOCS_PAGES, type DocsPageId } from "./registry";

/** Render the selected article with its breadcrumbs, metadata and page navigation. */
export function DocsArticle({
  pageId,
  mobile,
  menuOpen,
  onOpenMenu,
}: {
  pageId: DocsPageId;
  mobile: boolean;
  menuOpen: boolean;
  onOpenMenu(): void;
}) {
  const page = DOCS_PAGES[pageId];
  if (pageId === "home")
    return (
      <article key={pageId}>
        {mobile && (
          <DocsPageTools menuOpen={menuOpen} onOpenMenu={onOpenMenu} />
        )}
        <DocsBreadcrumbs pageId={pageId} />
        <DocsHome />
        <DocsPageNavigation pageId={pageId} />
      </article>
    );
  return (
    <article key={pageId}>
      {mobile && <DocsPageTools menuOpen={menuOpen} onOpenMenu={onOpenMenu} />}
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
