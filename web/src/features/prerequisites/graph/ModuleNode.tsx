/** Compact prerequisite-module boundary with graph-only marks and member expansion. */
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useProfileSelector } from "../../../state/useProfileSelector";
import { toggleNodeCompleted, toggleNodeExcluded } from "../actions";
import { useAction } from "../../../shared/useAction";
import type { GraphNodeData } from "./CourseNode";
import { ErrorNotice } from "../../../shared/ErrorNotice";
import { useWording } from "../../../shared/useWording";

export function ModuleNode({ data }: NodeProps & { data: GraphNodeData }) {
  const { store, value: manuallyCompleted } = useProfileSelector((state) =>
    state.prerequisites.completedNodeKeys.includes(data.actionKey),
  );
  const { value: excluded } = useProfileSelector((state) =>
    state.prerequisites.excludedNodeKeys.includes(data.actionKey),
  );
  const { runAction, error } = useAction();
  const { language, t } = useWording();
  const state = data.state;
  return (
    <div
      inert={data.interactionDisabled}
      className={`graph-module${manuallyCompleted || state?.completed_by_courses ? " done" : ""}${excluded ? " excl" : ""}`}
    >
      <Handle type="target" position={Position.Top} />
      <button
        className="graph-module-body"
        type="button"
        onClick={() => data.onMembers(data.id)}
      >
        <span className="graph-module-line">
          <span className="code">{t("module")}</span>
        </span>
        <b>{data.title}</b>
        <span className="graph-module-facts">
          <span>{data.subtitle} ▾</span>
        </span>
        {state?.completed_by_courses && !manuallyCompleted && (
          <i className="tile-tag">{t("fulfilled")}</i>
        )}
      </button>
      <div className="tile-actions nodrag nopan nowheel">
        <button
          type="button"
          className={manuallyCompleted ? "is-done" : ""}
          aria-pressed={manuallyCompleted}
          onClick={() =>
            runAction(() => toggleNodeCompleted(store, data.actionKey))
          }
        >
          {t(manuallyCompleted ? "Completed (course)" : "Complete (course)")}
        </button>
        <button
          type="button"
          className={excluded ? "is-excl" : ""}
          aria-pressed={excluded}
          onClick={() =>
            runAction(() => toggleNodeExcluded(store, data.actionKey))
          }
        >
          {t(excluded ? "Excluded" : "Exclude")}
        </button>
      </div>
      {error && <ErrorNotice error={error} language={language} />}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
