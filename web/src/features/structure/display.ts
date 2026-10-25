/**
 * Presentation-only flattening of transparent mandatory groups and the displayed place of a module
 * identity, without changing resolver identity.
 */
import type { CourseSummary } from "../../api/types";
import type { ResolvedNode, StructureNode } from "./model";

/** One resolved node's displayed courses, child nodes and notes. */
export type DisplayContents = {
  courses: { course: CourseSummary; added: boolean; owner: StructureNode }[];
  children: ResolvedNode[];
  notes: string[];
};

/** Flatten one resolved subtree into its displayed contents. */
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
 * Return the node whose displayed contents hold one course or child module identity, or null.
 *
 * The walk reads displayed children once per visited node, so a course inside a chosen option or a
 * transparent wrapper is attributed to the programme, module or Unplaced studies node that draws
 * it, and a module identity is attributed to its displayed parent.
 */
function contentSource(
  resolved: ResolvedNode,
  kind: "course" | "module",
  id: string,
): ResolvedNode | null {
  const contents = displayContents(resolved);
  if (
    kind === "course" &&
    contents.courses.some((item) => item.course.group_id === id)
  )
    return resolved;
  for (const child of contents.children) {
    if (kind === "module" && child.node.module?.group_id === id)
      return resolved;
    const found = contentSource(child, kind, id);
    if (found) return found;
  }
  return null;
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
  return contentSource(resolved, "module", moduleId);
}

/** Return the node whose displayed contents hold one course identity, or null when none does. */
export function courseSource(
  resolved: ResolvedNode,
  courseId: string,
): ResolvedNode | null {
  return contentSource(resolved, "course", courseId);
}
