/**
 * Presentation-only view of a resolved structure: flattened displayed contents, holder and course
 * order, and the node that displays a course or module.
 */
import type { CourseSummary } from "../../api/types";
import type { ResolvedNode } from "./model";

/** One resolved node's displayed courses, child nodes and notes. */
export type DisplayContents = {
  courses: { course: CourseSummary; added: boolean }[];
  children: ResolvedNode[];
  notes: string[];
};

/** Flatten one resolved subtree into its displayed contents. */
export function displayContents(resolved: ResolvedNode): DisplayContents {
  const result: DisplayContents = {
    courses: resolved.courses.map((item) => ({ ...item })),
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

/** The displayed entry of one loose Unplaced studies course, which no node places. */
const looseEntry = (course: CourseSummary) => ({ course, added: false });

/**
 * Return one Unplaced studies holder with the loose selected courses its drawer draws merged in.
 *
 * The drawer reads the node's own displayed courses and the courses it does not place, so the
 * courses keep the node's order and the loose ones follow without a rank.
 */
export function unplacedTarget(
  node: ResolvedNode,
  loose: readonly CourseSummary[],
): ResolvedNode {
  return {
    ...node,
    courses: [...node.courses, ...loose.map(looseEntry)],
    subtree: [...node.subtree, ...loose],
  };
}

/** One displayed holder: a programme, module or Unplaced studies node and its direct courses. */
export type DisplayedHolder = {
  key: string;
  node: ResolvedNode;
  courses: DisplayContents["courses"];
};

/** Return the displayed course holders in the depth-first order the tree draws them. */
export function displayedHolders(resolved: ResolvedNode): DisplayedHolder[] {
  const holders: DisplayedHolder[] = [];
  const walk = (node: ResolvedNode) => {
    const contents = displayContents(node);
    if (
      node.node.kind === "programme" ||
      node.node.kind === "module" ||
      node.node.kind === "unplaced"
    )
      holders.push({
        key: node.node.key,
        node,
        courses: contents.courses,
      });
    for (const child of contents.children) walk(child);
  };
  walk(resolved);
  return holders;
}

/**
 * Return the displayed courses ordered by their saved rank.
 *
 * A listed course ranks before an unlisted one, and courses that share a listed or an unlisted
 * rank keep their supplied relative order.
 */
export function orderCourses(
  courses: DisplayContents["courses"],
  order: readonly string[],
): DisplayContents["courses"] {
  const rank = new Map(order.map((id, index) => [id, index]));
  return courses
    .map((item, index) => ({ item, index }))
    .sort((left, right) => {
      const leftRank = rank.get(left.item.course.group_id);
      const rightRank = rank.get(right.item.course.group_id);
      if (leftRank === undefined && rightRank === undefined)
        return left.index - right.index;
      if (leftRank === undefined) return 1;
      if (rightRank === undefined) return -1;
      return leftRank - rightRank;
    })
    .map(({ item }) => item);
}

/**
 * Return one displayed holder's courses with its loose Unplaced studies courses merged in.
 *
 * Only the Unplaced studies holder draws selected courses it does not place, so every other holder
 * returns its own displayed courses. The result keeps the saved rank order.
 */
export function holderCourses(
  holder: ResolvedNode,
  courses: DisplayContents["courses"],
  loose: readonly CourseSummary[],
  order: readonly string[],
): DisplayContents["courses"] {
  const merged =
    holder.node.kind === "unplaced"
      ? [...courses, ...loose.map(looseEntry)]
      : courses;
  return orderCourses(merged, order);
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
