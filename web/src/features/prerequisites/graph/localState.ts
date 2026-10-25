/**
 * Evaluate the drawn box states from the held graph report and the live profile inputs.
 *
 * The cached report is never mutated: only the three live calculation sets are replaced on a
 * shallow copy, and every native table is shared by reference.
 */
import type {
  GraphNodeState,
  PrerequisiteGraphReport,
  PrerequisitesRequest,
} from "../../../api/types";
import { evaluateNodeStates } from "../../../solver/satisfaction";
import { withLiveInputs } from "../../../solver/structure";

/** Return the drawn box states of one report under the live profile inputs. */
export function evaluateGraphNodeStates(
  report: PrerequisiteGraphReport,
  request: PrerequisitesRequest,
): readonly GraphNodeState[] {
  const display = report.display;
  if (display === null) return [];
  const { structure, basis_group_ids: basis } = withLiveInputs(
    report.solver,
    request,
  );
  return evaluateNodeStates(
    structure,
    basis,
    display.nodes,
    request.completed_codes,
  );
}
