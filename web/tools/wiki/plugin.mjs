/**
 * Vite virtual-module plugin that builds the configured wiki and emits only selected local images.
 */
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { buildWiki, readWikiMeta } from "./build.mjs";

const virtualId = "virtual:wiki";
const resolvedVirtualId = `\0${virtualId}`;
const metaVirtualId = "virtual:wiki-meta";
const resolvedMetaVirtualId = `\0${metaVirtualId}`;

/** Return a Vite plugin that serves the configured wiki through virtual modules. */
export function wikiPlugin({
  repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../.."),
} = {}) {
  let sourceFiles = new Set();
  return {
    name: "configured-wiki",
    enforce: "pre",
    async resolveId(id) {
      if (id === virtualId) return resolvedVirtualId;
      if (id === metaVirtualId) return resolvedMetaVirtualId;
      return null;
    },
    async load(id) {
      if (id === resolvedMetaVirtualId) {
        const { repositoryUrl } = await readWikiMeta({ repoRoot });
        sourceFiles.add(resolve(repoRoot, "config/wiki.json"));
        return `export default ${JSON.stringify({ repositoryUrl })};`;
      }
      if (id !== resolvedVirtualId) return null;
      const { registry, assets } = await buildWiki({ repoRoot });
      const imports = [];
      const tokens = [];
      for (const [index, [token, file]] of Object.entries(assets).entries()) {
        imports.push(
          `import asset${index} from ${JSON.stringify(`${file}?url`)}`,
        );
        tokens.push([token, index]);
      }
      const pages = Object.fromEntries(
        Object.entries(registry.pages).map(([id, page]) => {
          let html = page.html;
          for (const [token, index] of tokens)
            html = html.replaceAll(token, `__WIKI_IMPORTED_ASSET_${index}__`);
          return [id, { ...page, html }];
        }),
      );
      const module =
        `${imports.join("\n")}\nconst pages = ${JSON.stringify(pages)};\n` +
        `const assets = [${tokens.map(([, index]) => `asset${index}`).join(",")}];\n` +
        `for (const page of Object.values(pages)) page.html = page.html.replace(/__WIKI_IMPORTED_ASSET_(\\d+)__/g, (_, index) => assets[Number(index)]);\n` +
        `export default ${JSON.stringify({ ...registry, pages: "__PAGES__" }).replace('"__PAGES__"', "pages")};`;
      sourceFiles = new Set([
        resolve(repoRoot, "config/wiki.json"),
        ...Object.values(registry.pages).map((page) =>
          resolve(repoRoot, page.sourcePath),
        ),
        ...Object.values(assets),
      ]);
      return module;
    },
    async handleHotUpdate({ file, server }) {
      if (!sourceFiles.has(resolve(file))) return;
      const modules = [];
      for (const id of [resolvedVirtualId, resolvedMetaVirtualId]) {
        const module = server.moduleGraph.getModuleById(id);
        if (module) {
          server.moduleGraph.invalidateModule(module);
          modules.push(module);
        }
      }
      return modules;
    },
    generateBundle() {
      for (const path of sourceFiles) this.addWatchFile(path);
    },
  };
}
