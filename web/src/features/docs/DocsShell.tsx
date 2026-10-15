/** Docs route shell joining native hash routing, persistent navigation, article and TOC. */
import { useEffect, useRef } from "react";
import { DOCS_PAGES } from "./registry";
import { useDocsRoute } from "./useDocsRoute";
import { DocsHeader } from "./DocsHeader";
import { DocsSidebar } from "./DocsSidebar";
import { DocsArticle } from "./DocsArticle";
import { DocsToc } from "./DocsToc";

export function DocsShell({ returnToApp }: { returnToApp: () => void }) {
  const { pageId, anchor } = useDocsRoute();
  const previousPage = useRef(pageId);
  const appTitle = useRef(document.title);
  useEffect(() => {
    document.documentElement.classList.add("docs-active");
    return () => {
      document.documentElement.classList.remove("docs-active");
      document.title = appTitle.current;
    };
  }, []);
  useEffect(() => {
    const routeMarkdownLink = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      const link = target.closest<HTMLAnchorElement>(
        ".docs-markdown a[href^='/docs#'], .docs-markdown-heading a.anc",
      );
      if (
        !link ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      )
        return;
      const [id, heading] = link.hash.slice(1).split("/", 2);
      if (!id || !DOCS_PAGES[decodeURIComponent(id)]) return;
      event.preventDefault();
      location.hash = heading
        ? `${decodeURIComponent(id)}/${decodeURIComponent(heading)}`
        : decodeURIComponent(id);
    };
    document.addEventListener("click", routeMarkdownLink);
    return () => document.removeEventListener("click", routeMarkdownLink);
  }, []);
  useEffect(() => {
    document.title =
      pageId === null
        ? "Page not found · TUNI Course Explorer docs"
        : pageId === "home"
          ? "Docs · TUNI Course Explorer"
          : `${DOCS_PAGES[pageId].title} · TUNI Course Explorer docs`;
    if (previousPage.current !== pageId) {
      window.scrollTo({ top: 0 });
      previousPage.current = pageId;
    }
    if (pageId && anchor)
      requestAnimationFrame(() =>
        document.getElementById(anchor)?.scrollIntoView({ behavior: "smooth" }),
      );
  }, [pageId, anchor]);
  return (
    <div className="docs-shell">
      <DocsHeader returnToApp={returnToApp} />
      <div
        className={`docs-layout${pageId === "home" || pageId === null ? " nohome" : ""}`}
      >
        <DocsSidebar pageId={pageId} />
        <main>
          {pageId ? (
            <DocsArticle pageId={pageId} />
          ) : (
            <article>
              <div className="docs-crumbs">
                <a href="/docs#home">{DOCS_PAGES.home.nav}</a>
              </div>
              <h1>Page not found</h1>
              <p className="docs-lead">
                This documentation page does not exist.
              </p>
              <a href="/docs#home">Return to documentation home</a>
            </article>
          )}
        </main>
        <DocsToc pageId={pageId} />
      </div>
    </div>
  );
}
