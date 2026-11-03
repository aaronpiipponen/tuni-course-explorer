/** The compact dataset role that one console summary read names. */
import type { DatasetRole } from "../api/types";
import { wording } from "./wording";

/** Render the role strip of one summary panel, with its Working-absent hint. */
export function DatasetRoleStatus({ role }: { role: DatasetRole | null }) {
  const detail = wording.datasets;
  if (role === "working") {
    return (
      <div className="roleStatus">
        <span className="tag ok">{detail.workingRole}</span>
      </div>
    );
  }
  if (role === "selected") {
    return (
      <div className="roleStatus">
        <span className="tag warn">{detail.selectedRole}</span>
        <span className="roleStatusNote">{detail.workingAbsentTitle}</span>
      </div>
    );
  }
  return (
    <div className="roleStatus">
      <span className="tag">{detail.noRole}</span>
    </div>
  );
}
