/** Compact prerequisite-module boundary with graph-only marks and member expansion. */
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useProfileSelector } from "../../../state/useProfileSelector";
import { toggleNodeCompleted, toggleNodeExcluded } from "../actions";
import { useAction } from "../../../shared/useAction";
import type { GraphNodeData } from "./CourseNode";
import { ErrorNotice } from "../../../shared/ErrorNotice";
import { useWording } from "../../../shared/useWording";

export function ModuleNode({ data }: NodeProps & { data: GraphNodeData }) {
  const { store } = useProfileSelector((state) => state.prerequisites);
  const { runAction, error } = useAction();
  const { language, t } = useWording();
  const state = data.state;
  return (
    <div
      inert={data.interactionDisabled}
      className={`graph-module${state?.completed_by_courses ? " done" : ""}${state?.is_excluded ? " excl" : ""}`}
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
        {state?.completed_by_courses && !state.manually_completed && (
          <i className="tile-tag">{t("fulfilled")}</i>
        )}
      </button>
      <div className="tile-actions nodrag nopan nowheel">
        <button
          type="button"
          className={state?.manually_completed ? "is-done" : ""}
          aria-pressed={state?.manually_completed ?? false}
          onClick={() =>
            runAction(() => toggleNodeCompleted(store, data.actionKey))
          }
        >
          {t(
            state?.manually_completed
              ? "Completed (course)"
              : "Complete (course)",
          )}
        </button>
        <button
          type="button"
          className={state?.is_excluded ? "is-excl" : ""}
          aria-pressed={state?.is_excluded ?? false}
          onClick={() =>
            runAction(() => toggleNodeExcluded(store, data.actionKey))
          }
        >
          {t(state?.is_excluded ? "Excluded" : "Exclude")}
        </button>
      </div>
      {error && <ErrorNotice error={error} language={language} />}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
