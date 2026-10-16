/** Build the explicit documentation allowlist into a transient typed wiki registry. */
import { readFile, realpath, stat } from "node:fs/promises";
import { resolve, relative, extname, dirname, sep } from "node:path";
import { unified } from "unified";
import remarkParse from "remark-parse";
import { visit } from "unist-util-visit";
import { compileMarkdown, resolveMarkdownReferences } from "./markdown.mjs";

const idPattern = /^[a-z0-9]+(?:-[a-z0-9]+)*$/u;
const maxNavDepth = 3;
const imageExtensions = new Set([
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".webp",
  ".svg",
]);
function fail(message) {
  throw new Error(`Wiki build: ${message}`);
}
function checkedText(value, label) {
  if (typeof value !== "string" || !value.trim())
    fail(`${label} must be nonblank text`);
  return value.trim();
}

function sourcePathFromConfig(value, label) {
  const sourcePath = checkedText(value, label);
  if (
    sourcePath.includes("\\") ||
    sourcePath.split("/").some((part) => !part || part === "." || part === "..")
  )
    fail(`${label} must be a normalized repository path`);
  return sourcePath;
}

export async function buildWiki({ repoRoot }) {
  const root = await realpath(repoRoot);
  const configPath = resolve(root, "config/wiki.json");
  let config;
  try {
    config = JSON.parse(await readFile(configPath, "utf8"));
  } catch (error) {
    fail(
      `cannot read config/wiki.json (${error instanceof SyntaxError ? "invalid JSON" : "read failed"})`,
    );
  }
  if (!config || typeof config !== "object" || Array.isArray(config))
    fail("config root must be an object");
  if (
    typeof config.repositoryUrl !== "string" ||
    typeof config.repositoryRef !== "string"
  )
    fail("repositoryUrl and repositoryRef are required");
  let repo;
  try {
    repo = new URL(config.repositoryUrl);
  } catch {
    fail("repositoryUrl must be a GitHub URL");
  }
  if (
    repo.protocol !== "https:" ||
    repo.hostname !== "github.com" ||
    repo.username ||
    repo.password ||
    repo.search ||
    repo.hash ||
    !/^\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/?$/u.test(repo.pathname)
  )
    fail("repositoryUrl must be credential-free HTTPS GitHub owner/repository");
  const repositoryUrl = repo.href.replace(/\/$/u, "").replace(/\.git$/u, "");
  const repositoryRef = checkedText(config.repositoryRef, "repositoryRef");
  const ids = new Set();
  const paths = new Set();
  const pages = [];
  function addPage(item, parent, section, depth) {
    if (!item || typeof item !== "object" || Array.isArray(item))
      fail("page must be an object");
    const id = checkedText(item.id, "page id");
    if (!idPattern.test(id) || ids.has(id))
      fail(`invalid or duplicate page id ${id}`);
    ids.add(id);
    if (depth > maxNavDepth)
      fail(`page ${id} is nested deeper than ${maxNavDepth} levels`);
    const path = sourcePathFromConfig(item.path, `path for ${id}`);
    if (paths.has(path) || path === "docs/USER-OWNED-TODO.md")
      fail(`duplicate or protected source path ${path}`);
    paths.add(path);
    const nav = checkedText(item.nav, `navigation label for ${id}`);
    if (nav.length > 32) fail(`navigation label for ${id} is too long`);
    const children = item.children ?? [];
    if (!Array.isArray(children)) fail(`children for ${id} must be an array`);
    const record = { id, path, nav, parent, section, childItems: children };
    pages.push(record);
    for (const child of children) addPage(child, id, section, depth + 1);
  }
  const home = config.home;
  if (!home || home.id !== "home") fail("home identity must be home");
  addPage({ ...home, children: [] }, null, null, 1);
  if (!Array.isArray(config.sections)) fail("sections must be an array");
  for (const section of config.sections) {
    const title = checkedText(section?.title, "section title");
    const description = checkedText(
      section?.description,
      `description for ${title}`,
    );
    if (!section.page || typeof section.page !== "object")
      fail(`page for ${title} must be an object`);
    addPage(section.page, null, { title, description }, 1);
  }
  if (
    !Array.isArray(config.popular) ||
    config.popular.some((id) => !ids.has(id))
  )
    fail("popular contains an unknown page id");
  if (new Set(config.popular).size !== config.popular.length)
    fail("popular contains duplicate page ids");
  const pageIdByPath = new Map(pages.map(({ id, path }) => [path, id]));
  const assets = {};
  const assetPathToToken = new Map();
  const directoryPaths = new Set();
  const selected = async (absolutePath, sourcePath) => {
    let actual;
    try {
      actual = await realpath(absolutePath);
    } catch {
      fail(`missing source ${sourcePath}`);
    }
    const rel = relative(root, actual);
    if (
      rel.startsWith(`..${sep}`) ||
      rel === ".." ||
      !actual.startsWith(`${root}${sep}`)
    )
      fail(`source escapes repository: ${sourcePath}`);
    if (
      !rel.startsWith(`docs${sep}`) ||
      extname(actual).toLowerCase() !== extname(sourcePath).toLowerCase()
    )
      fail(`source must be inside docs/: ${sourcePath}`);
    if (rel.split(sep).join("/") === "docs/USER-OWNED-TODO.md")
      fail("protected source path is not allowed");
    let info;
    try {
      info = await stat(actual);
    } catch {
      fail(`missing source ${sourcePath}`);
    }
    if (!info.isFile()) fail(`source must be a regular file: ${sourcePath}`);
    return {
      absolute: actual,
      repoPath: rel.split(sep).join("/"),
      updated: info.mtime.toISOString().slice(0, 10),
    };
  };
  const registryPages = {};
  for (const page of pages) {
    const { absolute, repoPath, updated } = await selected(
      resolve(root, page.path),
      page.path,
    );
    const source = await readFile(absolute, "utf8");
    const sourceDirectory = dirname(resolve(root, page.path));
    const resolveFrom = (destinationPath) =>
      destinationPath.startsWith("/")
        ? resolve(root, destinationPath.slice(1))
        : resolve(sourceDirectory, destinationPath);
    const sourceImageTokens = new Map();
    const ast = resolveMarkdownReferences(
      unified().use(remarkParse).parse(source),
    );
    const localImages = [];
    visit(ast, "image", (image) => localImages.push(image.url));
    const localLinks = [];
    visit(ast, "link", (link) => localLinks.push(link.url));
    for (const destination of localLinks) {
      if (/^(?:https?:|mailto:|\/\/)/iu.test(destination)) continue;
      const rawPath = destination.split("#", 1)[0];
      if (!rawPath) continue;
      const decodedPath = decodeURIComponent(rawPath);
      const resolvedPath = resolveFrom(decodedPath);
      const relativePath = relative(root, resolvedPath);
      if (relativePath.startsWith(`..${sep}`) || relativePath === "..")
        continue;
      const shaped =
        rawPath.endsWith("/") ||
        (!extname(decodedPath) &&
          !decodedPath.split(/[\\/]/u).at(-1)?.startsWith("."));
      if (shaped) {
        try {
          if ((await stat(resolvedPath)).isDirectory())
            directoryPaths.add(relativePath.split(sep).join("/"));
        } catch (error) {
          if (error.code !== "ENOENT" && error.code !== "ENOTDIR") throw error;
        }
      }
    }
    for (const destination of localImages) {
      if (/^(?:https?:|\/\/)/iu.test(destination)) continue;
      const imageFile = resolveFrom(
        decodeURIComponent(destination.split("#", 1)[0]),
      );
      if (destination.includes("#") || destination.includes("?"))
        fail(
          `local image fragments and queries are unsupported in ${page.path}`,
        );
      const imageRelative = relative(root, imageFile);
      if (imageRelative.startsWith(`..${sep}`) || imageRelative === "..")
        fail(`image escapes repository in ${page.path}`);
      const { absolute, repoPath: imageRepoPath } = await selected(
        imageFile,
        imageRelative.split(sep).join("/"),
      );
      if (!imageExtensions.has(extname(absolute).toLowerCase()))
        fail(`unsupported image in ${page.path}`);
      if (!assetPathToToken.has(absolute)) {
        const token = `__WIKI_ASSET_${assetPathToToken.size}__`;
        assetPathToToken.set(absolute, token);
        assets[token] = absolute;
      }
      const resolvedUrl = new URL(
        destination,
        `https://repo.invalid/${repoPath}`,
      );
      sourceImageTokens.set(
        resolvedUrl.pathname.slice(1),
        assetPathToToken.get(absolute),
      );
    }
    const compiled = await compileMarkdown({
      source,
      pageId: page.id,
      sourcePath: repoPath,
      pageIdByPath,
      repositoryUrl,
      repositoryRef,
      imageTokenByPath: sourceImageTokens,
      directoryPaths,
    });
    const children = page.childItems.map(({ id }) => id);
    registryPages[page.id] = {
      id: page.id,
      title: compiled.title,
      titleId: compiled.titleId,
      nav: page.nav,
      summary: compiled.summary,
      text: compiled.text,
      html: compiled.html,
      headings: compiled.headings,
      readingMinutes: compiled.readingMinutes,
      sourcePath: page.path,
      updated,
      children,
      parent: page.parent,
      section: page.section?.title ?? null,
    };
  }
  const sections = config.sections.map(({ title, description, page }) => ({
    title,
    description,
    page: page.id,
  }));
  const flattenIds = (page) => [
    page.id,
    ...(page.children ?? []).flatMap(flattenIds),
  ];
  const order = config.sections.flatMap(({ page }) => flattenIds(page));
  return {
    registry: {
      pages: registryPages,
      sections,
      order,
      popular: config.popular,
    },
    assets,
  };
}
