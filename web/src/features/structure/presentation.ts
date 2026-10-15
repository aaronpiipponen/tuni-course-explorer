/** Official module naming and minimum-credit display helpers for Structure. */
import type {
  CourseSummary,
  DisplayLanguage,
  ModuleSummary,
} from "../../api/types";
import { localizedName } from "../../shared/course/presentation";
import { uiText } from "../../shared/wording";

export function moduleName(
  module: ModuleSummary,
  language: DisplayLanguage,
): string {
  return localizedName(
    language,
    module.name_fi,
    module.name_en,
    module.code ?? module.group_id,
  );
}
export function nodeKindLabel(
  node: {
    kind: "programme" | "module" | "choice" | "group" | "unplaced";
  },
  language: DisplayLanguage,
): string {
  return uiText(language, node.kind);
}
export function formatCredits(n: number): string {
  return String(Number(n.toFixed(2)));
}
export function sumCredits(
  courses: readonly CourseSummary[],
  predicate: (course: CourseSummary) => boolean = () => true,
): number {
  return courses.reduce(
    (sum, course) => sum + (predicate(course) ? Number(course.credits_min) : 0),
    0,
  );
}
