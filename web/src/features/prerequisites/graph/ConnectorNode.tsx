/** Logical/numeric/unresolved node presentation, with actions only on markable constraints. */
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useProfileSelector } from "../../../state/useProfileSelector";
import { toggleNodeCompleted, toggleNodeExcluded } from "../actions";
import { useAction } from "../../../shared/useAction";
import type { GraphNodeData } from "./CourseNode";
import { ErrorNotice } from "../../../shared/ErrorNotice";
import { useWording } from "../../../shared/useWording";

/** Render one logical, numeric or unresolved node in the prerequisite drawing. */
export function ConnectorNode({ data }: NodeProps & { data: GraphNodeData }) {
  const markKey = data.markKey;
  const { value: completedAny } = useProfileSelector(
    (state) =>
      markKey !== null &&
      state.prerequisites.completedNodeKeys.includes(markKey),
  );
  const { value: excluded, store } = useProfileSelector(
    (state) =>
      markKey !== null &&
      state.prerequisites.excludedNodeKeys.includes(markKey),
  );
  const manuallyCompleted = completedAny && !excluded;
  const { runAction, error } = useAction();
  const { language, t } = useWording();
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
            className={manuallyCompleted ? "is-done" : ""}
            aria-pressed={manuallyCompleted}
            onClick={() =>
              markKey !== null &&
              runAction(() => toggleNodeCompleted(store, markKey))
            }
          >
            {t(manuallyCompleted ? "Completed (course)" : "Complete (course)")}
          </button>
          <button
            type="button"
            className={excluded ? "is-excl" : ""}
            aria-pressed={excluded}
            onClick={() =>
              markKey !== null &&
              runAction(() => toggleNodeExcluded(store, markKey))
            }
          >
            {t(excluded ? "Excluded" : "Exclude")}
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
