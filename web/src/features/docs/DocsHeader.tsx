/** Wiki header with native home/app links and the local docs search. */
import { DocsSearch } from "./DocsSearch";
import type { MouseEvent } from "react";

export function DocsHeader({ returnToApp }: { returnToApp: () => void }) {
  const returnOnOrdinaryClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    )
      return;
    event.preventDefault();
    returnToApp();
  };
  return (
    <header className="docs-header">
      <div className="docs-brand">
        <a className="docs-logo" href="/" onClick={returnOnOrdinaryClick}>
          <i>T</i>TUNI Course Explorer
        </a>
        <a
          className="docs-home-link"
          href="/docs#home"
          onClick={(event) => {
            if (
              event.button !== 0 ||
              event.metaKey ||
              event.ctrlKey ||
              event.shiftKey ||
              event.altKey
            )
              return;
            event.preventDefault();
            window.location.hash = "home";
          }}
        >
          Docs
        </a>
      </div>
      <DocsSearch />
      <div className="docs-right">
        <a
          className="docs-button primary"
          href="/"
          onClick={returnOnOrdinaryClick}
        >
          Back to the app
        </a>
      </div>
    </header>
  );
}
