/** Logical/numeric/unresolved node presentation, with actions only on numeric constraints. */
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useProfileSelector } from "../../../state/useProfileSelector";
import { toggleNodeCompleted, toggleNodeExcluded } from "../actions";
import { useAction } from "../../../shared/useAction";
import type { GraphNodeData } from "./CourseNode";
import { ErrorNotice } from "../../../shared/ErrorNotice";
import { useWording } from "../../../shared/useWording";

export function ConnectorNode({ data }: NodeProps & { data: GraphNodeData }) {
  const { store } = useProfileSelector((state) => state.activeTab);
  const { runAction, error } = useAction();
  const { language, t } = useWording();
  const state = data.state;
  const content = (
    <>
      <Handle type="target" position={Position.Top} />
      <button
        type="button"
        className={`graph-connector${data.subtype === "unresolved" ? " warn" : ""}`}
        title={data.subtitle || data.title}
        onClick={() => data.members && data.onMembers(data.id)}
      >
        {data.label ?? data.title}
      </button>
      {data.markable && (
        <div className="tile-actions">
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
      )}
      <Handle type="source" position={Position.Bottom} />
    </>
  );
  return (
    <div className="graph-connector-node" inert={data.interactionDisabled}>
      {content}
      {error && <ErrorNotice error={error} language={language} />}
    </div>
  );
}
