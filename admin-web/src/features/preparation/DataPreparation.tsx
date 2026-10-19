/**
 * The Data preparation tab: the three local stage panels and the owning report of each stage.
 *
 * Ingestion, translation and embedding each own one automatic status panel, and each stage's report
 * sits beside its own panel. Inference is a separate tab with its own status and actions.
 */
import { StagePanel, type SessionAccess } from "../../shared/StagePanel";
import { PreparationReport } from "./PreparationReport";

/** Render the Data preparation tab. */
export function DataPreparation({
  session,
  onRefusal,
}: {
  session: SessionAccess;
  onRefusal: (status: number) => void;
}) {
  return (
    <div>
      <div className="grid">
        <StagePanel stage="ingestion" session={session} onRefusal={onRefusal} />
        <StagePanel
          stage="translation"
          session={session}
          onRefusal={onRefusal}
        />
        <StagePanel stage="embedding" session={session} onRefusal={onRefusal} />
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
