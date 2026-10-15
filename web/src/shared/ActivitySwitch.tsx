/** Single "Active only" toggle chip for course activity scope. */
import { ToggleChip } from "./ToggleChip";
import { useWording } from "./useWording";

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
