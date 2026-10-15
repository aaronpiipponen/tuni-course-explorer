/** Compile selected repository Markdown to sanitized, GitHub-compatible wiki HTML and metadata. */
import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";
import remarkRehype from "remark-rehype";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import rehypeHighlight from "rehype-highlight";
import rehypeStringify from "rehype-stringify";
import GithubSlugger from "github-slugger";
import { visit } from "unist-util-visit";
import { toString } from "mdast-util-to-string";

export function resolveMarkdownReferences(tree) {
  const definitions = new Map();
  const definitionParents = new Set();
  visit(tree, "definition", (node) => definitions.set(node.identifier, node));
  visit(tree, "definition", (_node, _index, parent) => {
    if (parent) definitionParents.add(parent);
  });
  visit(tree, ["linkReference", "imageReference"], (node, index, parent) => {
    const definition = definitions.get(node.identifier);
    if (!definition || !parent || index === undefined) return;
    parent.children[index] = {
      type: node.type === "linkReference" ? "link" : "image",
      url: definition.url,
      title: definition.title,
      ...(node.type === "linkReference"
        ? { children: node.children }
        : { alt: toString(node) }),
    };
  });
  for (const parent of definitionParents)
    parent.children = parent.children.filter(
      (node) => node.type !== "definition",
    );
  return tree;
}

const ALERTS = new Map([
  ["NOTE", "note"],
  ["TIP", "tip"],
  ["IMPORTANT", "inf"],
  ["WARNING", "warn"],
  ["CAUTION", "warn"],
]);
function remarkWiki({
  pageId,
  sourcePath,
  pageIdByPath,
  repositoryUrl,
  repositoryRef,
  imageTokenByPath,
  directoryPaths,
}) {
  return (tree) => {
    resolveMarkdownReferences(tree);
    const slugger = new GithubSlugger();
    visit(tree, (node) => {
      if (node.type === "heading") {
        const text = toString(node);
        const id = slugger.slug(text);
        node.data = {
          ...node.data,
          hProperties: {
            ...node.data?.hProperties,
            id,
            className: node.depth === 2 ? ["docs-markdown-heading"] : undefined,
          },
        };
      }
      if (node.type === "blockquote") {
        const paragraph = node.children[0];
        const marker = paragraph?.type === "paragraph" && paragraph.children[0];
        const match =
          marker?.type === "text"
            ? /^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*/u.exec(
                marker.value,
              )
            : null;
        if (match) {
          const kind = ALERTS.get(match[1]);
          const labelText = match[1];
          marker.value = marker.value.slice(match[0].length);
          if (!marker.value) paragraph.children.shift();
          node.data = {
            ...node.data,
            hName: "div",
            hProperties: { className: ["callout", kind] },
          };
          paragraph.data = {
            ...paragraph.data,
            hName: "div",
            hProperties: { className: ["callout-body"] },
          };
          paragraph.children.unshift({
            type: "strong",
            data: { hName: "b" },
            children: [{ type: "text", value: labelText }],
          });
        }
      }
    });
    const resolveDestination = (destination, image) => {
      if (/^(?:https?:|mailto:|\/\/)/iu.test(destination))
        return { url: destination };
      const hashIndex = destination.indexOf("#");
      const rawPath =
        hashIndex < 0 ? destination : destination.slice(0, hashIndex);
      const fragment = hashIndex < 0 ? "" : destination.slice(hashIndex);
      if (!rawPath) return { url: `/docs#${pageId}/${fragment.slice(1)}` };
      const decoded = decodeURIComponent(rawPath);
      const resolved = new URL(decoded, `https://repo.invalid/${sourcePath}`);
      const path = resolved.pathname.slice(1);
      if (image) {
        const token = imageTokenByPath.get(path);
        if (!token)
          throw new Error(`Wiki build: unresolved local image ${path}`);
        return { url: token };
      }
      if (path.endsWith(".md")) {
        const target = pageIdByPath.get(path);
        if (target)
          return {
            url: `/docs#${target}${fragment ? `/${decodeURIComponent(fragment.slice(1))}` : ""}`,
          };
      }
      const directory = directoryPaths.has(path) || rawPath.endsWith("/");
      const url = `${repositoryUrl}/${directory ? "tree" : "blob"}/${encodeURIComponent(repositoryRef)}/${path.split("/").map(encodeURIComponent).join("/")}${fragment}`;
      return { url, external: true };
    };
    visit(tree, ["link", "definition", "image"], (node) => {
      if (node.url) {
        const mapped = resolveDestination(node.url, node.type === "image");
        node.url = mapped.url;
        if (mapped.external && node.type === "link") {
          node.data = {
            ...node.data,
            hProperties: {
              ...node.data?.hProperties,
              target: "_blank",
              rel: ["noopener", "noreferrer"],
            },
          };
        }
      }
    });
  };
}

export async function compileMarkdown({
  source,
  pageId,
  sourcePath,
  pageIdByPath,
  repositoryUrl,
  repositoryRef,
  imageTokenByPath = new Map(),
  directoryPaths = new Set(),
}) {
  const processor = unified()
    .use(remarkParse)
    .use(remarkGfm)
    .use(remarkWiki, {
      pageId,
      sourcePath,
      pageIdByPath,
      repositoryUrl,
      repositoryRef,
      imageTokenByPath,
      directoryPaths,
    })
    .use(remarkRehype, { allowDangerousHtml: false })
    .use(rehypeSanitize, {
      ...defaultSchema,
      clobberPrefix: "",
      attributes: {
        ...defaultSchema.attributes,
        "*": [
          ...(defaultSchema.attributes?.["*"] ?? []),
          "id",
          ["className", "docs-markdown-heading", "anc"],
        ],
        div: [
          ...(defaultSchema.attributes?.div ?? []),
          [
            "className",
            "callout",
            "note",
            "tip",
            "warn",
            "inf",
            "callout-body",
          ],
        ],
        h2: [...(defaultSchema.attributes?.h2 ?? [])],
        a: [
          ...(defaultSchema.attributes?.a ?? []),
          "aria-label",
          ["target", "_blank"],
          ["rel", "noopener", "noreferrer"],
        ],
      },
    })
    .use(rehypeHighlight, { detect: false })
    .use(() => (tree) => {
      visit(tree, "element", (node) => {
        if (node.tagName !== "h2") return;
        const id = node.properties.id;
        const title = toString(node);
        node.children.push({
          type: "element",
          tagName: "a",
          properties: {
            className: ["anc"],
            href: `/docs#${pageId}/${id}`,
            ariaLabel: `Link to ${title}`,
          },
          children: [{ type: "text", value: "#" }],
        });
      });
    })
    .use(rehypeStringify);
  const parsed = processor.parse(source);
  const slugger = new GithubSlugger();
  let title = pageId;
  let titleId = slugger.slug(title);
  let sawTitle = false;
  const headings = [];
  visit(parsed, "heading", (node) => {
    const authoredText = toString(node);
    const id = slugger.slug(authoredText);
    if (node.depth === 1 && !sawTitle) {
      sawTitle = true;
      title = authoredText;
      titleId = id;
    } else {
      if (node.depth === 2) headings.push({ id, title: authoredText });
    }
  });
  const summaryNode = parsed.children.find((node) => node.type === "paragraph");
  const summary = summaryNode ? toString(summaryNode) : "";
  const text = toString(parsed);
  const words = text.trim().split(/\s+/u).filter(Boolean).length;
  const metadata = await processor.run(parsed);
  const firstHeadingNode = metadata.children.find(
    (node) => node.type === "element" && node.tagName === "h1",
  );
  if (firstHeadingNode)
    metadata.children.splice(metadata.children.indexOf(firstHeadingNode), 1);
  const html = processor.stringify(metadata);
  return {
    title,
    titleId,
    summary: summary || text.split("\n")[0] || "",
    headings,
    html,
    text,
    readingMinutes: Math.max(1, Math.ceil(words / 200)),
  };
}
