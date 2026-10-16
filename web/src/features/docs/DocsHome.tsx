/** Wiki home with one card per configured section and the complete sanitized source body. */
import { DOCS_PAGES, DOCS_POPULAR, DOCS_SECTIONS } from "./registry";

export function DocsHome() {
  return (
    <>
      <div className="docs-hero">
        <h1 id={DOCS_PAGES.home.titleId}>{DOCS_PAGES.home.title}</h1>
        <div
          className="docs-markdown docs-home-markdown"
          dangerouslySetInnerHTML={{ __html: DOCS_PAGES.home.html }}
        />
      </div>
      <div className="docs-cards">
        {DOCS_SECTIONS.map((section) => (
          <a href={`/docs#${section.page}`} key={section.title}>
            <b>{section.title}</b>
            <span>{section.description}</span>
          </a>
        ))}
      </div>
      {DOCS_POPULAR.length > 0 && (
        <>
          <h2 className="docs-popular-title" id="popular">
            Popular pages
          </h2>
          <div className="docs-cards">
            {DOCS_POPULAR.map((id) => (
              <a href={`/docs#${id}`} key={id}>
                <b>{DOCS_PAGES[id].title}</b>
                <span>{DOCS_PAGES[id].summary}</span>
              </a>
            ))}
          </div>
        </>
      )}
    </>
  );
}
