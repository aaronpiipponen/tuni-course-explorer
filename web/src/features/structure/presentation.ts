/** Official module naming and minimum-credit display helpers for Structure. */
import type {
  CourseSummary,
  DisplayLanguage,
  ModuleSummary,
} from "../../api/types";
import type { ResolvedNode, StructureNode } from "./model";
import { localizedName } from "../../shared/course/presentation";
import { uiText } from "../../shared/wording";

/** Return the display name of one module, falling back to its code or identity. */
export function moduleName(
  module: Pick<ModuleSummary, "group_id" | "code" | "name_fi" | "name_en">,
  language: DisplayLanguage,
): string {
  return localizedName(
    language,
    module.name_fi,
    module.name_en,
    module.code ?? module.group_id,
  );
}
/** Return the localized name of one resolved node: its module name, its own title, or the choice fallback. */
export function resolvedNodeLabel(
  node: ResolvedNode,
  language: DisplayLanguage,
): string {
  return node.node.module
    ? moduleName(node.node.module, language)
    : (node.node.title ?? uiText(language, "Choice"));
}
/**
 * Return the noun one node's labels use, from the official degree type or the programme position.
 *
 * A degree programme reads as a programme wherever it sits, and a direct forest entry reads as a
 * programme from its position. The result selects words alone, never model kind, routing or
 * privileges.
 */
export function nodeWordingKind(
  node: Pick<StructureNode, "kind" | "module">,
): "programme" | "module" {
  return node.kind === "programme" ||
    node.module?.module_type === "DegreeProgramme"
    ? "programme"
    : "module";
}
/** Return the localized kind label of one node: its official type for a programme or module, its kind otherwise. */
export function nodeKindLabel(
  node: Pick<StructureNode, "kind" | "module">,
  language: DisplayLanguage,
): string {
  return uiText(
    language,
    node.kind === "programme" || node.kind === "module"
      ? node.module?.module_type === "DegreeProgramme"
        ? "programme"
        : "module"
      : node.kind,
  );
}
/** Return one credit value as text without trailing zeros. */
export function formatCredits(n: number): string {
  return String(Number(n.toFixed(2)));
}
/** Return the summed minimum credits of the courses the predicate accepts. */
export function sumCredits(
  courses: readonly CourseSummary[],
  predicate: (course: CourseSummary) => boolean = () => true,
): number {
  return courses.reduce(
    (sum, course) => sum + (predicate(course) ? Number(course.credits_min) : 0),
    0,
  );
}
