# Wiki compiler

The wiki compiler selects the configured Markdown pages, compiles them into sanitized HTML and metadata, and emits the registry the docs view renders.

## buildWiki and the selection

`buildWiki({ repoRoot })` in `web/tools/wiki/build.mjs` resolves the repository root with `realpath` and reads `config/wiki.json` from it. A read failure and invalid JSON each fail with one message.

The configuration is validated before any page is read:

- `repositoryUrl` must parse as an HTTPS `github.com` URL with no credentials, query or fragment and one owner and repository in the path, and `repositoryRef` must be nonblank text.
- `home.id` must be `home`, sections must be an array, and every section needs a nonblank title, a nonblank description and a `page` object that is validated as one of its pages.
- A page needs a nonblank `id` matching `^[a-z0-9]+(?:-[a-z0-9]+)*$` and unique across the selection, a `nav` of at most 32 characters, a source path, and an array of children.
- A source path holds no backslash and no empty, `.` or `..` segment, and is unique across the selection.
- A page nested deeper than `maxNavDepth` (3) fails the build.
- `popular` must be an array of known page identities with no duplicates.

`addPage` records each page with its `parent` identity, its section and its child items, then the pages are read in navigation order. The home page and each section's page are recorded with a null parent, and every other page is nested under its parent's `children`. The result carries the registry and the asset map: the registry holds `repositoryUrl` (the validated address without a trailing slash or `.git`), `pages`, `sections` (title, description and the section's page identity), `order` (each section's page followed by its descendants, section by section, with the home page left out) and `popular`.

## Source selection and containment

`selected(absolutePath, sourcePath)` resolves the destination with `realpath` first, so a symbolic link cannot satisfy the containment check. It fails when the destination is missing, when the resolved path is outside the repository root, when it is not inside `docs/`, when its extension differs from the extension in the configured path, and when it is not a regular file. It returns the resolved absolute path, the repository-relative path and `updated`, the source's modification time as a date. Every later read uses that resolved path.

## Markdown compilation

`compileMarkdown` in `web/tools/wiki/markdown.mjs` runs one unified pipeline: `remarkParse`, `remarkGfm`, the local `remarkWiki` plugin, `remarkRehype` with `allowDangerousHtml: false`, `rehypeSanitize` with an extended schema, `rehypeHighlight` with `detect: false`, one inline plugin that appends an anchor to each `h2`, and `rehypeStringify`.

`remarkWiki` does four things:

- `resolveMarkdownReferences` replaces link and image references with links and images built from their definitions and drops the definitions from the tree.
- One `GithubSlugger` gives every heading its id, and an `h2` also gets the `docs-markdown-heading` class.
- A blockquote whose first paragraph opens with `[!NOTE]`, `[!TIP]`, `[!IMPORTANT]`, `[!WARNING]` or `[!CAUTION]` becomes a `div` with the `callout` class and the kind class from `ALERTS` (`note`, `tip`, `inf` for IMPORTANT, and `warn` for WARNING and CAUTION). Its first paragraph becomes `div.callout-body` with the matched word as a leading bold label, and the marker itself is dropped.
- `resolveDestination` maps every link, definition and image destination.

The sanitize schema is `defaultSchema` with `clobberPrefix: ""`, `id` and the `docs-markdown-heading` and `anc` classes allowed on every element, the callout classes allowed on a `div`, and `target="_blank"` with `rel="noopener noreferrer"` allowed on an `a`.

The metadata pass reads the parsed tree: the first `h1` becomes `title` and its slug becomes `titleId` (the page id is the title when the page has no `h1`), every `h2` fills `headings`, the first top-level paragraph is the `summary` with the first line of the page text as a fallback, `text` is the whole document as plain text, and `readingMinutes` is the word count divided by 200, rounded up and at least one. The compiled `h1` element is left out of the HTML because `DocsArticle` renders the title itself.

## URL mapping

`resolveDestination(destination, image)` maps each destination:

| Destination | Result |
|---|---|
| `http:`, `https:`, `mailto:` or protocol-relative | Written as it is |
| A fragment with no path | `/docs#<pageId>/<fragment>` |
| A `.md` path that names a selected page | `/docs#<targetPageId>` with `/<heading>` when the link carries one |
| Any other path | `<repositoryUrl>/blob/<encoded ref>/<encoded segments>` with the fragment kept, and a link gets `target="_blank"` and `rel="noopener noreferrer"` |
| A path that names a directory, or one that ends with a slash | The same address with `tree` in place of `blob` |
| A local image path | Its asset token, and a path with no token fails the build |

A relative destination resolves against the page's repository path, and a destination that starts with one slash resolves against the repository root. A destination that starts with two slashes is protocol-relative and is left as it is. The path check `path.endsWith(".md")` runs before the repository fallback, so a Markdown file that is not selected becomes a GitHub address.

The directory set is collected in a pre-pass over the page's non-remote links: a link that ends with a slash, or that has no extension and whose last segment does not start with a dot, is `stat`ed, and a path that names a directory is recorded.

## Images, tokens and the Vite plugin

`buildWiki` visits every `image` node in the selected page. A remote destination is skipped. A local destination with a fragment or a query fails the build, a destination that resolves outside the repository fails, and the file goes through `selected`. An extension outside `imageExtensions` (`png`, `jpg`, `jpeg`, `gif`, `webp`, `svg`) fails the build. Each resolved path gets the token `__WIKI_ASSET_<n>__`, the assets map returns that token with the absolute path, and the image's URL in the page is replaced through `imageTokenByPath`, keyed by the resolved URL path of the page.

`wikiPlugin` in `web/tools/wiki/plugin.mjs` serves the `virtual:wiki` module. On `load` it runs `buildWiki`, imports each asset as `${file}?url`, replaces every token in the page HTML with `__WIKI_IMPORTED_ASSET_<index>__`, and emits a module that assigns the imported URLs back onto the HTML and exports the registry. `handleHotUpdate` invalidates the virtual module when a watched file changes, and `generateBundle` adds `config/wiki.json`, every selected page and every asset to the watch list.

## The registry and the docs view

The registry contracts are `DocsPage`, `DocsSection` and `DocsRegistry` in `web/src/features/docs/types.ts`, and `registry.ts` binds the virtual module and adds `isDocsPageId`, `getDocsNeighbours` and `getDocsAncestors`. A page carries its `title` and `titleId`, its `nav`, its `summary`, its `text` and `html`, its `headings`, its `readingMinutes`, its `sourcePath`, its `updated` date, its `children` identities, its `parent` identity and its `section` title. `DocsSection` carries the section `title`, its `description` and the `page` identity of the section's own page.

The view components:

- `useDocsRoute` reads `location.hash` as a page identity and an optional anchor, keeps its own state, and listens for `hashchange`.
- `DocsShell` routes a click on an in-page Markdown link and on a heading anchor by writing the hash, sets the document title, scrolls to the top on a page change, scrolls to an anchor, and renders the not-found article for an unknown identity.
- `DocsSidebar` renders the home entry and one header row per section with a toggle button and a link to the section page. It keeps the expanded section titles in a set, so each toggle opens and closes its own section, and it adds the current page's section when the page changes. The section link closes an open section without navigating when the section page is already the open page, and otherwise opens the section and navigates. A page below the section page opens its child group when it is the current page or an ancestor of it, through `getDocsAncestors`, and a closed group stays inert.
- `DocsArticle` renders the breadcrumbs, the title, the updated date and the reading time, the sanitized HTML and the page navigation. `DocsBreadcrumbs` builds the chain from the current page's parents, shows the home entry, the section title and the pages below the section page, and leaves the section title as plain text on the section page. `DocsHome` renders the home Markdown and one card per section with the section title and description.
- `DocsToc` observes the heading elements and marks the active one, `DocsPageNavigation` follows `DOCS_ORDER` through `getDocsNeighbours`, and `DocsSearch` matches the query against the title and the text of each page, ranks a title that starts with the query before one that contains it and both before a text-only match, and shows the extract around the first hit.
- `usePage` in `web/src/app/usePage.ts` owns the app and docs paths and their history entries, and `App` sets the document language to English while the docs path is open.

## Tests

| Test file | Covers |
|---|---|
| `web/tools/wiki/build.test.mjs` | Only configured pages in navigation order, a missing source and a source outside `docs/` all failing, an empty page built from source metadata, cross-page and same-page destinations, duplicated headings receiving distinct slugs, a script, an event handler and a `javascript:` address not reaching the HTML, three-level navigation with a fourth level failing, root-relative links and images from a nested page, the GitHub `blob` and `tree` fallbacks, a missing image failing, and external and protocol-relative destinations left alone |

## Where a change belongs

- A Markdown construct that should render differently belongs in the `remarkWiki` transform or in the sanitize schema in `markdown.mjs`.
- A destination form belongs in `resolveDestination`, and an image format belongs in `imageExtensions`.
- A registry field belongs in `buildWiki` and in `DocsPage`, and the component that shows it belongs beside the other view components.
- The page selection belongs in the wiki configuration, and the tracked template under `examples/config/` is what a fresh copy starts from.
