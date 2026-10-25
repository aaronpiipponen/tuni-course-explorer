/** Single "Active only" toggle chip for course activity scope. */
import { ToggleChip } from "./ToggleChip";
import { useWording } from "./useWording";

/** Render the Active only toggle for the course activity scope. */
export function ActivitySwitch({
  activeOnly,
  onChange,
}: {
  activeOnly: boolean;
  onChange: (activeOnly: boolean) => void;
}) {
  const { t } = useWording();
  return (
    <ToggleChip label={t("Active only")} on={activeOnly} onChange={onChange} />
  );
}
