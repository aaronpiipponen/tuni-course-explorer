/** The shared view type and state note of the retained-server summary panels. */
import type {
  DatasetReport,
  InferenceAdministrativeSummary,
} from "../../api/types";
import { wording } from "../../shared/wording";

/** The shared state of the one retained-server summary read. */
export interface SummaryView {
  scope: DatasetReport<InferenceAdministrativeSummary> | null;
  summary: InferenceAdministrativeSummary | null;
  lastSuccess: number | null;
  loading: boolean;
  selectionEnabled: boolean | "unavailable" | null;
  selectionFailure: string | null;
}

/** Render the summary panels' one state note when the site serves no usable selection. */
export function SummaryStateNote({ view }: { view: SummaryView }) {
  if (view.selectionEnabled === false)
    return <p className="note">{wording.selectionDisabled}</p>;
  if (view.selectionEnabled === "unavailable")
    return <p className="warn-note">{wording.stateUnavailable}</p>;
  return null;
}
