/** buildWiki allowlist, link identity and sanitized-output contracts. */
import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, stat, utimes, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { buildWiki } from "./build.mjs";

async function selectedTree(t, { files, config }) {
  const root = await mkdtemp(join(tmpdir(), "wiki-build-test-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(join(root, "config"), { recursive: true });
  await writeFile(join(root, "config/wiki.json"), JSON.stringify(config));
  for (const [path, text] of Object.entries(files)) {
    await mkdir(dirname(join(root, path)), { recursive: true });
    await writeFile(join(root, path), text);
  }
  return root;
}

function config() {
  return {
    repositoryUrl: "https://github.com/owner/repo",
    repositoryRef: "main",
    home: { id: "home", path: "docs/guide/home.md", nav: "Home" },
    sections: [
      {
        title: "Guides",
        description: "Selected guides.",
        pages: [
          {
            id: "page",
            path: "docs/guide/page.md",
            nav: "Guide",
            children: [],
          },
        ],
      },
    ],
    popular: ["page"],
  };
}

test("publishes only config-listed documents in navigation order", async (t) => {
  const root = await selectedTree(t, {
    config: config(),
    files: {
      "docs/guide/home.md": "# Home\n\nWelcome.",
      "docs/guide/page.md": "# Page\n\nListed text.",
      "docs/guide/unlisted.md": "# Unlisted\n\nPrivate selection.",
    },
  });
  const { registry } = await buildWiki({ repoRoot: root });
  assert.deepEqual(Object.keys(registry.pages), ["home", "page"]);
  assert.deepEqual(registry.order, ["page"]);
  assert.equal(registry.pages.page.nav, "Guide");
  assert.equal(registry.pages.home.summary, "Welcome.");
  assert.equal(registry.pages.page.text.includes("Listed text."), true);
  assert.equal(registry.pages.page.text.includes("Private selection"), false);

  const missing = config();
  missing.sections[0].pages[0].path = "docs/guide/absent.md";
  const missingRoot = await selectedTree(t, {
    config: missing,
    files: { "docs/guide/home.md": "# Home\n\nWelcome." },
  });
  await assert.rejects(
    () => buildWiki({ repoRoot: missingRoot }),
    /missing source docs\/guide\/absent\.md/u,
  );

  const outside = config();
  outside.home.path = "README.md";
  const outsideRoot = await selectedTree(t, {
    config: outside,
    files: {
      "README.md": "# Root\n\nNot a wiki source.",
      "docs/guide/page.md": "# Page\n\nListed text.",
    },
  });
  await assert.rejects(
    () => buildWiki({ repoRoot: outsideRoot }),
    /source must be inside docs\//u,
  );

  const protectedSource = config();
  protectedSource.sections[0].pages[0].path = "docs/USER-OWNED-TODO.md";
  const protectedRoot = await selectedTree(t, {
    config: protectedSource,
    files: {
      "docs/guide/home.md": "# Home\n\nWelcome.",
      "docs/USER-OWNED-TODO.md":
        "# Synthetic placeholder\n\nNot the user-owned file.\n",
    },
  });
  await assert.rejects(
    () => buildWiki({ repoRoot: protectedRoot }),
    /protected source path/u,
  );
});

test("builds an empty Home from a plain directory using source metadata", async (t) => {
  const root = await selectedTree(t, {
    config: {
      repositoryUrl: "https://github.com/owner/repo",
      repositoryRef: "main",
      home: { id: "home", path: "docs/placeholder.md", nav: "Home" },
      sections: [],
      popular: [],
    },
    files: { "docs/placeholder.md": "" },
  });
  const stamp = new Date(Date.UTC(2026, 3, 5, 12, 30));
  await utimes(join(root, "docs/placeholder.md"), stamp, stamp);
  await assert.rejects(() => stat(join(root, ".git")));

  const { registry } = await buildWiki({ repoRoot: root });
  assert.deepEqual(Object.keys(registry.pages), ["home"]);
  assert.deepEqual(registry.sections, []);
  assert.deepEqual(registry.order, []);
  assert.deepEqual(registry.popular, []);
  assert.equal(registry.pages.home.updated, "2026-04-05");
  assert.equal(registry.pages.home.text, "");
  assert.equal(registry.pages.home.html, "");
});

test("preserves Markdown cross-page and heading destinations", async (t) => {
  const settings = config();
  settings.sections[0].pages[0].path = "docs/guide/first.md";
  settings.sections[0].pages[0].children = [
    { id: "second", path: "docs/guide/second.md", nav: "Second", children: [] },
  ];
  const root = await selectedTree(t, {
    config: settings,
    files: {
      "docs/guide/home.md": "# Home\n\nWelcome.",
      "docs/guide/first.md":
        "# First\n\nFirst summary.\n\n[Second](second.md#two) and [source](unlisted.md#part). [Referenced second][second]. [Referenced source][source]. [Same-page](#two).\n\n[second]: second.md#two\n[source]: unlisted.md#part\n\n## Déjà Vu\n\n## Déjà Vu\n\n## Two\n",
      "docs/guide/second.md": "# Second\n\nSecond summary.\n\n## Two\n",
      "docs/guide/unlisted.md": "# Unlisted\n\nSource.",
    },
  });
  const { registry } = await buildWiki({ repoRoot: root });
  const first = registry.pages.page;
  assert.match(first.html, /href="\/docs#second\/two"/u);
  assert.match(first.html, /href="\/docs#page\/two"/u);
  assert.match(
    first.html,
    /href="https:\/\/github\.com\/owner\/repo\/blob\/main\/docs\/guide\/unlisted\.md#part" target="_blank" rel="noopener noreferrer"/u,
  );
  assert.deepEqual(
    first.headings.slice(0, 2).map(({ id }) => id),
    ["déjà-vu", "déjà-vu-1"],
  );
});

test("does not turn Markdown into executable HTML", async (t) => {
  const root = await selectedTree(t, {
    config: config(),
    files: {
      "docs/guide/home.md": "# Home\n\nWelcome.",
      "docs/guide/page.md":
        '# Page\n\nSummary.\n\n<script>alert(1)</script>\n\n<img src=x onerror="alert(1)">\n\n[bad](javascript:alert%281%29) and [good](https://example.com).',
    },
  });
  const { registry } = await buildWiki({ repoRoot: root });
  const html = registry.pages.page.html;
  assert.doesNotMatch(html, /<script|onerror|javascript:/iu);
});

test("supports three-level navigation and rejects deeper nesting", async (t) => {
  const settings = config();
  settings.sections[0].pages[0].children = [
    {
      id: "child",
      path: "docs/guide/child.md",
      nav: "Child",
      children: [
        {
          id: "grandchild",
          path: "docs/guide/grandchild.md",
          nav: "Grandchild",
          children: [],
        },
      ],
    },
  ];
  const root = await selectedTree(t, {
    config: settings,
    files: {
      "docs/guide/home.md": "# Home\n\nWelcome.",
      "docs/guide/page.md": "# Page\n\nTop.",
      "docs/guide/child.md": "# Child\n\nMiddle.",
      "docs/guide/grandchild.md": "# Grandchild\n\nDeep.",
    },
  });
  const { registry } = await buildWiki({ repoRoot: root });
  assert.deepEqual(registry.order, ["page", "child", "grandchild"]);
  assert.deepEqual(registry.pages.page.children, ["child"]);
  assert.deepEqual(registry.pages.child.children, ["grandchild"]);
  assert.equal(registry.pages.grandchild.parent, "child");
  assert.equal(registry.pages.grandchild.section, "Guides");
  assert.equal(registry.pages.grandchild.text.includes("Deep."), true);

  const deep = config();
  deep.sections[0].pages[0].children = [
    {
      id: "child",
      path: "docs/guide/child.md",
      nav: "Child",
      children: [
        {
          id: "grandchild",
          path: "docs/guide/grandchild.md",
          nav: "Grandchild",
          children: [
            {
              id: "great",
              path: "docs/guide/great.md",
              nav: "Great",
              children: [],
            },
          ],
        },
      ],
    },
  ];
  const deepRoot = await selectedTree(t, {
    config: deep,
    files: {
      "docs/guide/home.md": "# Home\n\nWelcome.",
      "docs/guide/page.md": "# Page\n\nTop.",
    },
  });
  await assert.rejects(
    () => buildWiki({ repoRoot: deepRoot }),
    /nested deeper than 3/u,
  );
});
