/** Official choice option row: the main button selects it. Only a course also has its own Complete button. */
import type { StructureOption } from "./model";
import type { DisplayLanguage } from "../../state/types";
import { courseCredits, courseName } from "../../shared/course/presentation";
import { moduleName } from "./presentation";
import { uiText } from "../../shared/wording";

function cells(
  option: StructureOption,
  language: DisplayLanguage,
): [string, string, string] {
  if (option.entries.length !== 1)
    return [
      "",
      uiText(language, "{count} items", { count: option.entries.length }),
      "",
    ];
  const entry = option.entries[0];
  if (entry.kind === "course")
    return [
      entry.course.code,
      courseName(entry.course, language),
      courseCredits(entry.course, language),
    ];
  if (entry.kind === "note") return ["", entry.text, ""];
  if (entry.node.module)
    return [
      entry.node.module.code ?? "",
      moduleName(entry.node.module, language),
      entry.node.rule,
    ];
  return ["", entry.node.title ?? "", entry.node.rule];
}

export function DrawerOptionRow({
  option,
  selected,
  language,
  onChoose,
  completion,
  disabled = false,
}: {
  option: StructureOption;
  selected: boolean;
  language: DisplayLanguage;
  onChoose(): void;
  completion?: { completed: boolean; onToggle(): void };
  disabled?: boolean;
}) {
  const [code, name, rule] = cells(option, language);
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
            completion.completed ? "Mark not completed" : "Mark completed",
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
