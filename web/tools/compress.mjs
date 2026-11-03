/** Vite plugin that writes a Brotli and a gzip variant beside every text asset in the build. */
import { readdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { brotliCompressSync, constants, gzipSync } from "node:zlib";

const textExtensions = new Set([
  ".js",
  ".mjs",
  ".css",
  ".html",
  ".json",
  ".svg",
]);

function isText(name) {
  const dot = name.lastIndexOf(".");
  return dot >= 0 && textExtensions.has(name.slice(dot).toLowerCase());
}

async function compressFile(path) {
  const source = await readFile(path);
  await Promise.all([
    writeFile(
      `${path}.br`,
      brotliCompressSync(source, {
        params: { [constants.BROTLI_PARAM_QUALITY]: 9 },
      }),
    ),
    writeFile(`${path}.gz`, gzipSync(source, { level: 9 })),
  ]);
}

async function walk(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) await walk(path);
    else if (entry.isFile() && isText(entry.name)) await compressFile(path);
  }
}

/**
 * Build the Vite plugin that writes a Brotli and a gzip variant beside every text asset of the
 * bundle.
 *
 * The plugin runs after the bundle is written and walks the output directory Vite supplies. A build
 * without an output directory writes no variant.
 */
export function compressPlugin() {
  return {
    name: "precompress-assets",
    enforce: "post",
    async writeBundle(options) {
      if (options.dir) await walk(options.dir);
    },
  };
}
