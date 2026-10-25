/** Persistent config-driven wiki navigation with independently collapsible sections that open their own page. */
import { useCallback, useEffect, useRef, useState } from "react";
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
  mobile,
}: {
  id: DocsPageId;
  pageId: DocsPageId | null;
  ancestors: ReadonlySet<DocsPageId>;
  depth: number;
  mobile: boolean;
}) {
  const page = DOCS_PAGES[id];
  const open = pageId === id || ancestors.has(id);
  const [mobileOpen, setMobileOpen] = useState(open);
  useEffect(() => {
    if (open) setMobileOpen(true);
  }, [open]);
  const hasChildren = page.children.length > 0;
  const expanded = mobile ? mobileOpen : open;
  if (mobile && hasChildren)
    return (
      <div>
        <button
          type="button"
          className={`docs-branch-title${depth > 1 ? " sub" : ""}${expanded ? " open" : ""}`}
          data-depth={depth}
          aria-expanded={expanded}
          onClick={() => setMobileOpen((value) => !value)}
        >
          <span>{page.nav}</span>
          <i aria-hidden="true">›</i>
        </button>
        <div
          className={`docs-subs${expanded ? " open" : ""}`}
          inert={!expanded}
        >
          <div>
            <a
              className={`sub${pageId === id ? " on" : ""}`}
              data-depth={depth + 1}
              href={`/docs#${id}`}
              aria-current={pageId === id ? "page" : undefined}
            >
              Overview
            </a>
            {page.children.map((child) => (
              <SidebarBranch
                key={child}
                id={child}
                pageId={pageId}
                ancestors={ancestors}
                depth={depth + 1}
                mobile={mobile}
              />
            ))}
          </div>
        </div>
      </div>
    );
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
                mobile={mobile}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** Render the configured page tree and reveal the selected page's ancestors. */
export function DocsSidebar({
  pageId,
  mobile = false,
}: {
  pageId: DocsPageId | null;
  mobile?: boolean;
}) {
  const navigation = useRef<HTMLElement>(null);
  const ancestors = new Set(pageId ? getDocsAncestors(pageId) : []);
  const currentSection = pageId ? DOCS_PAGES[pageId].section : null;
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(
    () => new Set(currentSection ? [currentSection] : []),
  );
  const revealCurrent = useCallback(() => {
    const nav = navigation.current;
    const current = nav?.querySelector<HTMLElement>('[aria-current="page"]');
    if (!nav || !current || current.closest("[inert]")) return;
    const viewport = nav.getBoundingClientRect();
    const item = current.getBoundingClientRect();
    if (item.top < viewport.top) nav.scrollTop += item.top - viewport.top;
    else if (item.bottom > viewport.bottom)
      nav.scrollTop += item.bottom - viewport.bottom;
  }, []);
  useEffect(revealCurrent, [pageId, expanded, revealCurrent]);
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
    <aside
      className="docs-nav"
      ref={navigation}
      onTransitionEnd={(event) => {
        if (event.propertyName === "grid-template-rows") revealCurrent();
      }}
    >
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
              {mobile ? (
                <button
                  className="docs-section-title"
                  type="button"
                  aria-expanded={open}
                  onClick={() => toggle(section.title)}
                >
                  <span>{section.title}</span>
                  <i aria-hidden="true">›</i>
                </button>
              ) : (
                <>
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
                </>
              )}
            </h6>
            <div className={`docs-subs${open ? " open" : ""}`} inert={!open}>
              <div>
                {mobile && root.children.length > 0 && (
                  <a
                    className={`overview${pageId === section.page ? " on" : ""}`}
                    href={`/docs#${section.page}`}
                    aria-current={pageId === section.page ? "page" : undefined}
                  >
                    Overview
                  </a>
                )}
                {root.children.map((id) => (
                  <SidebarBranch
                    key={id}
                    id={id}
                    pageId={pageId}
                    ancestors={ancestors}
                    depth={1}
                    mobile={mobile}
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
