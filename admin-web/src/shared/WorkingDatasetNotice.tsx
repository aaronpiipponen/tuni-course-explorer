/** The one Working-dataset notice a stage tab carries when the inventory reports none. */
import { wording } from "./wording";

/** Render the notice, or nothing while a Working dataset is present or unknown. */
export function WorkingDatasetNotice({ absent }: { absent: boolean }) {
  if (!absent) {
    return null;
  }
  const detail = wording.datasets;
  return (
    <div className="datasetNotice" role="status">
      <span className="datasetNoticeMark" aria-hidden="true">
        !
      </span>
      <div className="datasetNoticeText">
        <b>{detail.workingAbsentTitle}</b>
        <span>{detail.workingAbsentHint}</span>
      </div>
    </div>
  );
}
