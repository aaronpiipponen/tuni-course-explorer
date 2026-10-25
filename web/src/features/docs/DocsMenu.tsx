/** Mobile documentation menu: search, the nested page structure and the repository link. */
import { useEffect, type MouseEvent } from "react";
import { useMediaQuery } from "../../shared/useMediaQuery";
import { PHONE_SHELL_QUERY } from "../../shared/viewport";
import { GITHUB_MARK } from "../../shared/icons";
import { DocsSearch } from "./DocsSearch";
import { DocsSidebar } from "./DocsSidebar";
import { DOCS_REPOSITORY_URL } from "./registry";
import type { DocsPageId } from "./registry";

/** Render the mobile navigation dialog with search and the repository link. */
export function DocsMenu({
  open,
  pageId,
  onClose,
}: {
  open: boolean;
  pageId: DocsPageId | null;
  onClose(): void;
}) {
  useEffect(() => {
    if (!open) return;
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", keydown);
    return () => document.removeEventListener("keydown", keydown);
  }, [open, onClose]);
  const mobile = useMediaQuery(PHONE_SHELL_QUERY);
  const closeOnPageLink = (event: MouseEvent<HTMLElement>) => {
    if (
      event.target instanceof Element &&
      event.target.closest('a[href^="/docs#"]')
    )
      onClose();
  };
  return (
    <>
      <div
        className={`docs-menu-scrim${open ? " open" : ""}`}
        aria-hidden="true"
        onClick={onClose}
      />
      <aside
        id="docs-menu"
        className={`docs-menu${open ? " open" : ""}`}
        role="dialog"
        aria-label="Documentation menu"
        aria-hidden={!open}
        inert={!open}
        onClick={closeOnPageLink}
      >
        <div className="docs-menu-search">
          <DocsSearch shortcut={open} />
          <button
            className="pill-btn docs-menu-close"
            type="button"
            onClick={onClose}
          >
            Close
          </button>
        </div>
        <div className="docs-menu-body">
          <DocsSidebar pageId={pageId} mobile={mobile} />
        </div>
        <div className="docs-menu-foot">
          <a
            className="docs-button docs-github"
            href={DOCS_REPOSITORY_URL}
            target="_blank"
            rel="noopener noreferrer"
          >
            {GITHUB_MARK}
            GitHub
          </a>
        </div>
      </aside>
    </>
  );
}
