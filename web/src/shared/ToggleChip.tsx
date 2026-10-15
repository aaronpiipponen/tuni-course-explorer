/** Persistable one-action toggle styled as a compact graph chip. */
export function ToggleChip({
  label,
  on,
  onChange,
}: {
  label: string;
  on: boolean;
  onChange: (on: boolean) => void;
}) {
  return (
    <button
      type="button"
      className={`toggle-chip${on ? " on" : ""}`}
      aria-pressed={on}
      onClick={() => onChange(!on)}
    >
      {label}
    </button>
  );
}
