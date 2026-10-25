/** Ephemeral plain-substring search over generated page titles and Markdown text, title matches first. */
import { useEffect, useRef, useState } from "react";
import { DOCS_ORDER, DOCS_PAGES, type DocsPageId } from "./registry";

/**
 * Return the pages whose title or text contains the query, title matches first.
 *
 * A title that starts with the query ranks before a title that contains it, and both rank before
 * a page that matches only in its text. Pages in the same rank keep their navigation order.
 */
function matchPages(query: string): { id: DocsPageId; snippet: string }[] {
  if (!query) return [];
  const ranked = ["home", ...DOCS_ORDER].flatMap((id) => {
    const page = DOCS_PAGES[id];
    const title = page.title.toLocaleLowerCase();
    const text = `${page.title} ${page.text}`;
    const at = text.toLocaleLowerCase().indexOf(query);
    if (!title.includes(query) && at < 0) return [];
    const rank = title.startsWith(query) ? 0 : title.includes(query) ? 1 : 2;
    const snippet =
      at >= 0
        ? `…${text.slice(Math.max(0, at - 40), at + 90)}…`
        : (page.section ?? "");
    return [{ id, snippet, rank }];
  });
  return ranked
    .sort((a, b) => a.rank - b.rank)
    .map(({ id, snippet }) => ({ id, snippet }));
}

/** Render title-ranked documentation search with an optional keyboard shortcut. */
export function DocsSearch({ shortcut = true }: { shortcut?: boolean }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const value = query.trim().toLocaleLowerCase();
  const matches = matchPages(value);

  useEffect(() => {
    const outside = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const keys = (event: KeyboardEvent) => {
      const target = event.target;
      const editable =
        target instanceof HTMLElement &&
        (target.isContentEditable ||
          /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName));
      if (
        shortcut &&
        event.key === "/" &&
        !editable &&
        target !== input.current
      ) {
        event.preventDefault();
        input.current?.focus();
      }
      if (event.key === "Escape") {
        setOpen(false);
        input.current?.blur();
      }
    };
    document.addEventListener("click", outside);
    document.addEventListener("keydown", keys);
    return () => {
      document.removeEventListener("click", outside);
      document.removeEventListener("keydown", keys);
    };
  }, [shortcut]);

  return (
    <div className="docs-search" ref={root}>
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-3.5-3.5" />
      </svg>
      <input
        ref={input}
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
        }}
        onFocus={() => {
          if (value) setOpen(true);
        }}
        placeholder="Search the docs"
        autoComplete="off"
        aria-label="Search the docs"
      />
      <div className={`docs-results${open && value ? " open" : ""}`}>
        {matches.length ? (
          matches.map(({ id, snippet }) => (
            <a
              key={id}
              href={`/docs#${id}`}
              onClick={() => {
                setOpen(false);
                setQuery("");
              }}
            >
              <em>{DOCS_PAGES[id].title}</em>
              <small>{snippet}</small>
            </a>
          ))
        ) : (
          <span className="docs-no-results">
            No pages match “{query.trim()}”.
          </span>
        )}
      </div>
    </div>
  );
}
