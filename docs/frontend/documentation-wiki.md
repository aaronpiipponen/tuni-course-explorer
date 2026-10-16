# Documentation wiki

Docs renders the project's Markdown pages inside the app from a fixed selection, in English and without a profile.

## The pages the configuration selects

The wiki shows the Markdown files that the wiki configuration names, in the order it names them. The configuration holds one home page and a list of sections. Each section has a title, a description and one page of its own, and the section's remaining pages are nested under that page. A page may hold children, and a child may hold children of its own, so the navigation reaches three levels with the section's page at the first. Every page entry carries a navigation label, which is the word the sidebar, the breadcrumbs and the previous and next links show.

Only the named files are part of the wiki, and every other repository file is read on GitHub instead. The tracked template is `examples/config/wiki.json`, and the file a running copy reads is the ignored `config/wiki.json` that is copied from the template at setup. Changing the selection changes the wiki of that copy alone. [Configuration](/docs/backend/configuration.md) lists the wiki configuration with the other configuration files.

The excerpt below is taken from the tracked template. It shows one section with its page and the page's two children, with the repository and home fields and the other sections left out.

```json
{
  "sections": [
    {
      "title": "Architecture",
      "description": "The parts of the system, how they connect, and the boundaries between them.",
      "page": {
        "id": "architecture",
        "path": "docs/architecture/README.md",
        "nav": "Architecture overview",
        "children": [
          {
            "id": "system-context",
            "path": "docs/architecture/system-context.md",
            "nav": "System context",
            "children": []
          },
          {
            "id": "boundaries",
            "path": "docs/architecture/boundaries.md",
            "nav": "System boundaries",
            "children": []
          }
        ]
      }
    }
  ]
}
```

The diagram follows the selection, the build and the reading of a page.

![The wiki configuration, the selected Markdown pages and the local images they reference feed the wiki build compiler, which produces the page records of the registry that the wiki reader shows. A dashed arrow marks that a link to a file the wiki does not render becomes an address in the GitHub repository.](/docs/diagrams/wiki-build.svg)

## Reading a page

A page's title is its first top-level heading, and its summary is its first paragraph. The home page shows the home Markdown, then one card for each configured section with the section title and its description, and each card opens the section's page. When the configuration lists popular pages, the home page adds a **Popular pages** panel with one card for each, showing its title and summary. Under the title a page shows the date of its source file and the reading time computed from its length, counted at 200 words a minute and never shorter than one minute.

Every heading carries a slug built from its text, so the same heading twice on one page gets distinct slugs. A heading can be linked from anywhere in the wiki or from a page on GitHub.

Above the article, breadcrumbs lead from the home page through the section title and the pages below the section page. On the section's own page the crumb is the home label and the section title with no link on the title. Beside the article, the sidebar lists the home entry above one row for each section, and a section row carries a toggle button and a link that opens the section's page. The toggle opens and closes its section on its own, so several sections can be open at once, and a section opens when the open page is in it. Selecting the link of an open section while its own page is the open page closes the section and leaves the reader on the page. A page with children inside a section opens its child group only while that page or one of its descendants is the open page. Below the article, the previous and next links follow the configuration order, so the first page of the wiki follows the home page. The "On this page" list beside the article gives the page's second-level headings and marks the one the reader is at.

An address holds the page identity in the hash, with the heading as an optional second part. An identity the configuration does not hold shows a not-found page with a link to the home page.

## The search

The search reads the compiled page text in the browser and matches a plain substring, ignoring case, in the title or in the text of the home page and every selected page. The results list pages whose title starts with the query first, then pages whose title contains it, then pages that match only in their text, and the pages inside each group keep the navigation order. A match shows the title and a short extract of the text around the match. The `/` key focuses the field, and Escape closes the results.

## Links from a page

The author writes repository links with a leading slash, and the build rewrites them for the reader.

| Link in a page | What the reader gets |
|---|---|
| A page the configuration names | That page in the wiki, at the named heading when the link carries a heading |
| A heading on the same page | The heading on the page |
| Any other file in the repository | The file's address in the project's GitHub repository, opened in another browser tab |
| A repository folder | The folder's address in the project's GitHub repository, opened in another browser tab |
| An external site | The address as the author wrote it |

The build turns a link to a named page into a wiki route and a link to any other file into a GitHub address. The selected sources are checked and the destinations a page links to are not, so every link and its heading is the author's to verify.

## Images

An image a page embeds from the repository is bundled into the wiki build and served with the app, whether the path is written from the repository root or relative to the page. A named image that the build cannot find, and an image in an unsupported format, fail the build. An image on an external site is left as the author wrote it.

## The Markdown the wiki renders

The wiki renders GitHub-flavored Markdown. A table is drawn as a table and a fenced code block is highlighted by the language tag on its fence. A table scrolls sideways when a cell holds a word wider than the article, and neither a table cell nor an inline code span inside a cell breaks a word in the middle.

A blockquote that opens with `[!NOTE]`, `[!TIP]`, `[!IMPORTANT]`, `[!WARNING]` or `[!CAUTION]` becomes one callout of that kind, and the kind word labels it. WARNING and CAUTION share one style.

Page markup is sanitized before the app shows it, so a script element, an inline event handler and a `javascript:` link address are dropped and the rest of the page is rendered.

## Seeing an edit

The build reads the selected files when the app is built, so a served copy shows an edit after the app is built again. A development server rebuilds the registry when a selected page, the configuration file or a bundled image changes.

## The wiki in the app

The wiki is English only, and its own controls are English whatever the profile language is. It opens from **Docs**, and **Back to the app** and the brand in its header return to the app. A page is compiled text with its images, so the app renders it from the built registry. Opening the wiki writes no profile field, so the open tab and the course sets are there when the app returns.

The build, its selection rules, its Markdown pipeline and the tests that cover it are described in [Wiki compiler](/docs/frontend/wiki-compiler.md).
