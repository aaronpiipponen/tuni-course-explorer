/** Persistent config-driven wiki navigation with inert animated child groups. */
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
  return (
    <aside className="docs-nav">
      <a
        className={`home${pageId === "home" ? " on" : ""}`}
        href="/docs#home"
        aria-current={pageId === "home" ? "page" : undefined}
      >
        {DOCS_PAGES.home.nav}
      </a>
      {DOCS_SECTIONS.map((section) => (
        <div className="docs-nav-section" key={section.title}>
          <h6>{section.title}</h6>
          {section.pages.map((id) => (
            <SidebarBranch
              key={id}
              id={id}
              pageId={pageId}
              ancestors={ancestors}
              depth={1}
            />
          ))}
        </div>
      ))}
    </aside>
  );
}
