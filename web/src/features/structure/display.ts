/** Presentation-only flattening of transparent mandatory groups without changing resolver identity. */
import type { CourseSummary } from "../../api/types";
import type { ResolvedNode, StructureNode } from "./model";

export type DisplayContents = {
  courses: { course: CourseSummary; added: boolean; owner: StructureNode }[];
  children: ResolvedNode[];
  notes: string[];
};

export function displayContents(resolved: ResolvedNode): DisplayContents {
  const result: DisplayContents = {
    courses: resolved.courses.map((item) => ({
      ...item,
      owner: resolved.node,
    })),
    children: [],
    notes: [...resolved.notes],
  };
  const appendVisible = (child: ResolvedNode) => {
    if (child.node.kind === "choice" || child.node.transparent) {
      const nested = displayContents(child);
      result.courses.push(...nested.courses);
      result.children.push(...nested.children);
      result.notes.push(...nested.notes);
      return;
    }
    result.children.push(child);
  };
  for (const child of resolved.children) {
    appendVisible(child);
  }
  return result;
}
