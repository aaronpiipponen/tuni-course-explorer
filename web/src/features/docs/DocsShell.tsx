/** Docs route shell joining native hash routing, persistent navigation, article and TOC. */
import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "../../shared/useReducedMotion";
import { DOCS_PAGES } from "./registry";
import { useDocsRoute } from "./useDocsRoute";
import { DocsHeader } from "./DocsHeader";
import { DocsSidebar } from "./DocsSidebar";
import { DocsArticle } from "./DocsArticle";
import { DocsMenu } from "./DocsMenu";
import { DocsPageTools } from "./DocsPageTools";
import { useMediaQuery } from "../../shared/useMediaQuery";
import { PHONE_SHELL_QUERY } from "../../shared/viewport";
import { DocsToc } from "./DocsToc";

/** Render the documentation route with responsive navigation and heading links. */
export function DocsShell({ returnToApp }: { returnToApp: () => void }) {
  const { pageId, anchor } = useDocsRoute();
  const mobile = useMediaQuery(PHONE_SHELL_QUERY);
  const [menuOpen, setMenuOpen] = useState(false);
  const reducedMotion = useReducedMotion();
  const previousPage = useRef(pageId);
  const appTitle = useRef(document.title);
  useEffect(() => {
    setMenuOpen(false);
  }, [pageId]);
  useEffect(() => {
    document.documentElement.classList.toggle("docs-menu-open", menuOpen);
    return () => document.documentElement.classList.remove("docs-menu-open");
  }, [menuOpen]);
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
        document.getElementById(anchor)?.scrollIntoView({
          behavior: reducedMotion ? "instant" : "smooth",
        }),
      );
  }, [pageId, anchor, reducedMotion]);
  return (
    <div className="docs-shell">
      <DocsHeader returnToApp={returnToApp} mobile={mobile} />
      {mobile && (
        <DocsMenu
          open={menuOpen}
          pageId={pageId}
          onClose={() => setMenuOpen(false)}
        />
      )}
      <div
        className={`docs-layout${pageId === "home" || pageId === null ? " nohome" : ""}`}
      >
        {!mobile && <DocsSidebar pageId={pageId} />}
        <main>
          {pageId ? (
            <DocsArticle
              pageId={pageId}
              mobile={mobile}
              menuOpen={menuOpen}
              onOpenMenu={() => setMenuOpen(true)}
            />
          ) : (
            <article>
              {mobile && (
                <DocsPageTools
                  menuOpen={menuOpen}
                  onOpenMenu={() => setMenuOpen(true)}
                />
              )}
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
