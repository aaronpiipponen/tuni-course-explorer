/**
 * The Data preparation tab: the three local stage panels and the owning report of each stage.
 *
 * Ingestion, translation and embedding each own one automatic status panel, and each stage's report
 * sits beside its own panel. Each report reads Working first, falls back to Selected and names the
 * role it read. Inference is a separate tab with its own status and actions.
 */
import { StagePanel, type SessionAccess } from "../../shared/StagePanel";
import { WorkingDatasetNotice } from "../../shared/WorkingDatasetNotice";
import { PreparationReport } from "./PreparationReport";

/** Render the Data preparation tab. */
export function DataPreparation({
  session,
  onRefusal,
  workingPresent,
}: {
  session: SessionAccess;
  onRefusal: (status: number) => void;
  workingPresent: boolean | null;
}) {
  return (
    <div>
      <WorkingDatasetNotice absent={workingPresent === false} />
      <div className="grid">
        <StagePanel
          stage="ingestion"
          session={session}
          onRefusal={onRefusal}
          workingPresent={workingPresent}
        />
        <StagePanel
          stage="translation"
          session={session}
          onRefusal={onRefusal}
          workingPresent={workingPresent}
        />
        <StagePanel
          stage="embedding"
          session={session}
          onRefusal={onRefusal}
          workingPresent={workingPresent}
        />
      </div>
      <div className="grid">
        <PreparationReport
          kind="catalogue"
          session={session}
          onRefusal={onRefusal}
        />
        <PreparationReport
          kind="teaching-text"
          session={session}
          onRefusal={onRefusal}
        />
        <PreparationReport
          kind="embedding"
          session={session}
          onRefusal={onRefusal}
        />
      </div>
    </div>
  );
}
