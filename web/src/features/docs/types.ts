/** Build-generated wiki registry contracts consumed by the docs feature. */
export type DocsPageId = string;
export type DocsHeading = { id: string; title: string };
export type DocsPage = {
  id: DocsPageId;
  title: string;
  titleId: string;
  nav: string;
  summary: string;
  text: string;
  html: string;
  readingMinutes: number;
  sourcePath: string;
  /** Direct subpages in configuration order. Nesting may reach three levels. */
  children: readonly DocsPageId[];
  parent: DocsPageId | null;
  section: string | null;
  headings: readonly DocsHeading[];
  updated: string;
};
export type DocsSection = {
  title: string;
  description: string;
  /** The page the section opens on, with every other page of the section nested below it. */
  page: DocsPageId;
};
export type DocsRegistry = {
  pages: Readonly<Record<DocsPageId, DocsPage>>;
  sections: readonly DocsSection[];
  order: readonly DocsPageId[];
  popular: readonly DocsPageId[];
};
