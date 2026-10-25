/** Shared fixture loaders and result readers for the TypeScript route tests. */
import type {
  GraphDisplay,
  GraphDisplayNode,
  PathCourse,
  SolverStructure,
} from "../api/types";
import { parseCredits } from "./credits";

/** One fixture entry: a solver structure and the display of its source compilation. */
export type RouteFixtureEntry = {
  solver: SolverStructure;
  display: GraphDisplay | null;
};

/** One route fixture file keyed by test structure label. */
export type RouteFixtures = Record<string, RouteFixtureEntry>;

/** Return one fixture's solver structure. An unknown label throws. */
export function loadStructure(
  fixtures: RouteFixtures,
  label: string,
): SolverStructure {
  const entry = fixtures[label];
  if (entry === undefined) {
    throw new Error(`unknown route fixture ${label}`);
  }
  return entry.solver;
}

/**
 * Return one fixture's drawn display. An unknown label or a missing display throws.
 */
export function loadDisplay(
  fixtures: RouteFixtures,
  label: string,
): GraphDisplay {
  const entry = fixtures[label];
  if (entry === undefined) {
    throw new Error(`unknown route fixture ${label}`);
  }
  if (entry.display === null) {
    throw new Error(`route fixture ${label} has no display`);
  }
  return entry.display;
}

/** Return the selected canonical course IDs of one result. */
export function selectedGroupIds(result: {
  new_courses: readonly PathCourse[];
}): string[] {
  return result.new_courses.map((entry) => entry.course.group_id);
}

/** Return one decimal credit string as hundredths, or `null`. */
export function creditsOf(text: string | null): number | null {
  return text === null ? null : parseCredits(text);
}

/** Return every drawn course node. */
export function courseNodes(display: GraphDisplay): GraphDisplayNode[] {
  return display.nodes.filter((node) => node.kind === "course");
}
