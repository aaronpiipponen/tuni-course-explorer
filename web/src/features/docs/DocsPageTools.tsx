/** The mobile article search and documentation menu trigger above the breadcrumb chain. */
import { DocsSearch } from "./DocsSearch";

function DocsMenuTrigger({ open, onOpen }: { open: boolean; onOpen(): void }) {
  return (
    <button
      className="docs-menu-trigger"
      type="button"
      aria-label="Documentation menu"
      aria-haspopup="dialog"
      aria-expanded={open}
      aria-controls="docs-menu"
      onClick={onOpen}
    >
      <svg viewBox="0 0 16 16" aria-hidden="true">
        <path d="M2 4h12M2 8h12M2 12h12" />
      </svg>
    </button>
  );
}

/** Render mobile article search and the documentation menu control. */
export function DocsPageTools({
  menuOpen,
  onOpenMenu,
}: {
  menuOpen: boolean;
  onOpenMenu(): void;
}) {
  return (
    <div className="docs-page-tools">
      <DocsSearch shortcut={!menuOpen} />
      <DocsMenuTrigger open={menuOpen} onOpen={onOpenMenu} />
    </div>
  );
}
