/** Type declaration for the compiler-owned virtual wiki module. */
declare module "virtual:wiki" {
  import type { DocsRegistry } from "./types";
  const registry: DocsRegistry;
  export default registry;
}
