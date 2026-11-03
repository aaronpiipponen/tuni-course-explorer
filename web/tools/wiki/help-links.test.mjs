/** The app's in-page documentation links resolve to a configured page and one of its headings. */
import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import { join, relative } from "node:path";
import test from "node:test";
import GithubSlugger from "github-slugger";
import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";
import { visit } from "unist-util-visit";
import { toString } from "mdast-util-to-string";

const ROOT = join(import.meta.dirname, "..", "..", "..");
const LINK = /\/docs#([a-z0-9-]+)\/([a-z0-9-]+)/gu;

async function sourceFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...(await sourceFiles(path)));
    else if (/\.(ts|tsx)$/u.test(entry.name)) files.push(path);
  }
  return files;
}

async function pageIds() {
  const selection = JSON.parse(
    await readFile(join(ROOT, "examples/config/wiki.json"), "utf8"),
  );
  const ids = new Map();
  function walk(node) {
    ids.set(node.id, node.path);
    for (const child of node.children ?? []) walk(child);
  }
  walk(selection.home);
  for (const section of selection.sections) walk(section.page);
  return ids;
}

async function headingIds(path) {
  const tree = unified()
    .use(remarkParse)
    .use(remarkGfm)
    .parse(await readFile(join(ROOT, path), "utf8"));
  const slugger = new GithubSlugger();
  const ids = new Set();
  visit(tree, "heading", (node) => {
    ids.add(slugger.slug(toString(node)));
  });
  return ids;
}

test("every in-app documentation link names a configured page and one of its headings", async () => {
  const ids = await pageIds();
  const links = [];
  for (const directory of ["web/src", "admin-web/src"]) {
    for (const file of await sourceFiles(join(ROOT, directory))) {
      const text = await readFile(file, "utf8");
      for (const match of text.matchAll(LINK)) {
        links.push({
          file: relative(ROOT, file),
          pageId: match[1],
          anchor: match[2],
        });
      }
    }
  }
  assert.ok(links.length > 0, "the app declares no documentation links");
  for (const link of links) {
    const path = ids.get(link.pageId);
    assert.ok(path, `${link.file} names the unconfigured page ${link.pageId}`);
    assert.ok(
      (await headingIds(path)).has(link.anchor),
      `${link.file} links to the missing heading ${link.pageId}/${link.anchor}`,
    );
  }
});
