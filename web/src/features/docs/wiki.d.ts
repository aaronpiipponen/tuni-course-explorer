/** Type declaration for the compiler-owned virtual wiki modules. */
declare module "virtual:wiki" {
  import type { DocsRegistry } from "./types";
  const registry: DocsRegistry;
  export default registry;
}

declare module "virtual:wiki-meta" {
  const meta: { repositoryUrl: string };
  export default meta;
}
