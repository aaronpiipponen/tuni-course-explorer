/** Wiki home with configured section panels and the complete sanitized source body. */
import {
  DOCS_PAGES,
  DOCS_POPULAR,
  DOCS_SECTIONS,
  type DocsPageId,
} from "./registry";

function HomePageLink({ id }: { id: DocsPageId }) {
  const page = DOCS_PAGES[id];
  return (
    <li>
      <a href={`/docs#${id}`}>{page.nav}</a>
      {page.children.length > 0 && (
        <ul>
          {page.children.map((child) => (
            <HomePageLink key={child} id={child} />
          ))}
        </ul>
      )}
    </li>
  );
}

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
      {DOCS_SECTIONS.map((section) => (
        <section className="docs-sec" key={section.title}>
          <h3>{section.title}</h3>
          <p>{section.description}</p>
          <ul>
            {section.pages.map((id) => (
              <HomePageLink key={id} id={id} />
            ))}
          </ul>
        </section>
      ))}
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
