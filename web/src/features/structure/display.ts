/**
 * Presentation-only flattening of transparent mandatory groups and the displayed place of a module
 * identity, without changing resolver identity.
 */
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

/**
 * Return the node whose displayed children hold one module identity, or null when none does.
 *
 * The walk reads displayed children, so a module inside a chosen option or a transparent wrapper is
 * attributed to the programme, module or Unplaced studies node that the tree draws it in.
 */
export function moduleSource(
  resolved: ResolvedNode,
  moduleId: string,
): ResolvedNode | null {
  for (const child of displayContents(resolved).children) {
    if (child.node.module?.group_id === moduleId) return resolved;
    const found = moduleSource(child, moduleId);
    if (found) return found;
  }
  return null;
}
