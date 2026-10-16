/** Persistent config-driven wiki navigation with independently collapsible sections that open their own page. */
import { useEffect, useState } from "react";
import {
  DOCS_PAGES,
  DOCS_SECTIONS,
  getDocsAncestors,
  type DocsPageId,
} from "./registry";

function SidebarBranch({
  id,
  pageId,
  ancestors,
  depth,
}: {
  id: DocsPageId;
  pageId: DocsPageId | null;
  ancestors: ReadonlySet<DocsPageId>;
  depth: number;
}) {
  const page = DOCS_PAGES[id];
  const open = pageId === id || ancestors.has(id);
  const hasChildren = page.children.length > 0;
  return (
    <div>
      <a
        className={`${hasChildren ? "has" : ""}${depth > 1 ? " sub" : ""}${pageId === id ? " on" : ""}${open ? " open" : ""}`}
        data-depth={depth}
        href={`/docs#${id}`}
        aria-current={pageId === id ? "page" : undefined}
        aria-expanded={hasChildren ? open : undefined}
      >
        {page.nav}
        {hasChildren && <i aria-hidden="true">›</i>}
      </a>
      {hasChildren && (
        <div className={`docs-subs${open ? " open" : ""}`} inert={!open}>
          <div>
            {page.children.map((child) => (
              <SidebarBranch
                key={child}
                id={child}
                pageId={pageId}
                ancestors={ancestors}
                depth={depth + 1}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function DocsSidebar({ pageId }: { pageId: DocsPageId | null }) {
  const ancestors = new Set(pageId ? getDocsAncestors(pageId) : []);
  const currentSection = pageId ? DOCS_PAGES[pageId].section : null;
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(
    () => new Set(currentSection ? [currentSection] : []),
  );
  useEffect(() => {
    if (currentSection)
      setExpanded((previous) =>
        previous.has(currentSection)
          ? previous
          : new Set(previous).add(currentSection),
      );
  }, [currentSection]);
  const toggle = (title: string) =>
    setExpanded((previous) => {
      const next = new Set(previous);
      if (!next.delete(title)) next.add(title);
      return next;
    });
  return (
    <aside className="docs-nav">
      <a
        className={`home${pageId === "home" ? " on" : ""}`}
        href="/docs#home"
        aria-current={pageId === "home" ? "page" : undefined}
      >
        {DOCS_PAGES.home.nav}
      </a>
      {DOCS_SECTIONS.map((section) => {
        const open = expanded.has(section.title);
        const root = DOCS_PAGES[section.page];
        return (
          <div className="docs-nav-section" key={section.title}>
            <h6 className={pageId === section.page ? "on" : undefined}>
              <button
                type="button"
                aria-expanded={open}
                aria-label={section.title}
                onClick={() => toggle(section.title)}
              >
                <i aria-hidden="true">›</i>
              </button>
              <a
                href={`/docs#${section.page}`}
                aria-current={pageId === section.page ? "page" : undefined}
                onClick={(event) => {
                  if (open && pageId === section.page) {
                    event.preventDefault();
                    toggle(section.title);
                  } else if (!open) toggle(section.title);
                }}
              >
                {section.title}
              </a>
            </h6>
            <div className={`docs-subs${open ? " open" : ""}`} inert={!open}>
              <div>
                {root.children.map((id) => (
                  <SidebarBranch
                    key={id}
                    id={id}
                    pageId={pageId}
                    ancestors={ancestors}
                    depth={1}
                  />
                ))}
              </div>
            </div>
          </div>
        );
      })}
    </aside>
  );
}
