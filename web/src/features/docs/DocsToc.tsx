/** Generated-heading on-page navigation with scroll observation. */
import { useEffect, useState } from "react";
import { DOCS_PAGES, type DocsPageId } from "./registry";

export function DocsToc({ pageId }: { pageId: DocsPageId | null }) {
  const headings = pageId ? DOCS_PAGES[pageId].headings : [];
  const [active, setActive] = useState<string | null>(null);
  useEffect(() => {
    setActive(null);
    if (!headings.length) return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries)
          if (entry.isIntersecting) setActive(entry.target.id);
      },
      { rootMargin: "-80px 0px -70% 0px" },
    );
    headings.forEach(({ id }) => {
      const element = document.getElementById(id);
      if (element) observer.observe(element);
    });
    return () => observer.disconnect();
  }, [pageId, headings]);
  return (
    <aside className="docs-toc">
      <h6>On this page</h6>
      {pageId !== "home" && pageId !== null && (
        <>
          <div>
            {headings.map(({ id, title }) => (
              <a
                key={id}
                className={active === id ? "on" : ""}
                href={`/docs#${pageId}/${id}`}
              >
                {title}
              </a>
            ))}
          </div>
        </>
      )}
    </aside>
  );
}
