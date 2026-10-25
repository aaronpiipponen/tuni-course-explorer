/** Animated module/internal-option member list reusing the shared official course cards. */
import { useAction } from "../../../shared/useAction";
import { CourseListRow } from "../../../shared/course/CourseListRow";
import { useFreeChoiceAdd } from "../../structure/useFreeChoiceAdd";
import type { ModelNode } from "./model";
import { ErrorNotice } from "../../../shared/ErrorNotice";
import { Disclosure } from "../../../shared/Disclosure";
import { useWording } from "../../../shared/useWording";

/** Render the member list of one module or requirement disclosure box. */
export function MemberPanel({
  node,
  onClose,
}: {
  node: ModelNode | null;
  onClose: () => void;
}) {
  const { runAction, error } = useAction();
  const { language, t } = useWording();
  const members = node?.members ?? [];
  const freeChoice = useFreeChoiceAdd();
  return (
    <Disclosure open={node !== null} className="member-panel">
      <aside>
        <div className="member-panel-top">
          <div>
            <small>{t("members")}</small>
            <b>{node?.title}</b>
            <span>
              {t(
                members.length === 1
                  ? "total · {count} course"
                  : "total · {count} courses",
                { count: members.length },
              )}
            </span>
          </div>
          <button className="pill-btn" type="button" onClick={onClose}>
            {t("Close")}
          </button>
        </div>
        {error && <ErrorNotice error={error} language={language} />}
        <div className="list member-list">
          {members.map((course) => (
            <CourseListRow key={course.group_id} course={course} />
          ))}
        </div>
        {node?.kind === "module" && (
          <button
            className="pill-btn member-add"
            type="button"
            onClick={() =>
              runAction(() =>
                freeChoice.add(members.map((course) => course.group_id)),
              )
            }
          >
            {t("Add all module courses to structure")}
          </button>
        )}
      </aside>
    </Disclosure>
  );
}
