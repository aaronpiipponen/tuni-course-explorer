/** Ephemeral plain-substring search over generated page titles and Markdown text. */
import { useEffect, useRef, useState } from "react";
import { DOCS_ORDER, DOCS_PAGES } from "./registry";

export function DocsSearch() {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const value = query.trim().toLocaleLowerCase();
  const matches = value
    ? ["home", ...DOCS_ORDER].flatMap((id) => {
        const page = DOCS_PAGES[id];
        const text = `${page.title} ${page.text}`;
        const at = text.toLocaleLowerCase().indexOf(value);
        return page.title.toLocaleLowerCase().includes(value) || at >= 0
          ? [
              {
                id,
                snippet:
                  at >= 0
                    ? `…${text.slice(Math.max(0, at - 40), at + 90)}…`
                    : (page.section ?? ""),
              },
            ]
          : [];
      })
    : [];

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
      if (event.key === "/" && !editable && target !== input.current) {
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
  }, []);

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
      <kbd>/</kbd>
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
