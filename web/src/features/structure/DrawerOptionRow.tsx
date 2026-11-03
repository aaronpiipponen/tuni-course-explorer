/**
 * Official choice option row whose main button selects the option and, for a course, completes it.
 */
import type { StructureEntry } from "./model";
import type { DisplayLanguage } from "../../state/types";
import { courseCredits, courseName } from "../../shared/course/presentation";
import { moduleName } from "./presentation";
import { uiText } from "../../shared/wording";

function cells(
  entry: Exclude<StructureEntry, { kind: "note" }>,
  language: DisplayLanguage,
): [string, string, string] {
  if (entry.kind === "course")
    return [
      entry.course.code,
      courseName(entry.course, language),
      courseCredits(entry.course, language),
    ];
  if (entry.node.module)
    return [
      entry.node.module.code ?? "",
      moduleName(entry.node.module, language),
      entry.node.rule,
    ];
  return ["", entry.node.title ?? "", entry.node.rule];
}

/** Render one official choice option row with its course completion button. */
export function DrawerOptionRow({
  entry,
  selected,
  language,
  onChoose,
  completion,
  disabled = false,
}: {
  entry: Exclude<StructureEntry, { kind: "note" }>;
  selected: boolean;
  language: DisplayLanguage;
  onChoose(): void;
  completion?: { completed: boolean; onToggle(): void };
  disabled?: boolean;
}) {
  const [code, name, rule] = cells(entry, language);
  return (
    <div className={`prow opt${selected ? " cur" : ""}`}>
      <button
        className="prow-main"
        type="button"
        disabled={disabled}
        onClick={onChoose}
      >
        <span className="code">{code}</span>
        <span className="pn">{name}</span>
        <span className="cr">{rule}</span>
      </button>
      {completion ? (
        <button
          className={`add drawer-selection-toggle${completion.completed ? " is-done" : ""}`}
          type="button"
          aria-pressed={completion.completed}
          aria-label={uiText(
            language,
            completion.completed ? "Remove completion" : "Mark completed",
          )}
          disabled={disabled}
          onClick={completion.onToggle}
        >
          {uiText(
            language,
            completion.completed ? "Completed (course)" : "Complete (course)",
          )}
        </button>
      ) : null}
    </div>
  );
}
