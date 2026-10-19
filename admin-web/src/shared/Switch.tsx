/**
 * Render the console's shared on/off switch.
 *
 * One switch renders one boolean the operator toggles, with its accessible name and its disabled
 * state. Its styling is the panel's own switch rule, so the feature switches and every other boolean
 * choice look and behave the same.
 */

/** Render one boolean toggle for a control that is known to hold a boolean. */
export function Switch({
  label,
  checked,
  disabled = false,
  onChange,
}: {
  label: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <button
      className={`switch${checked ? " on" : ""}`}
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
    />
  );
}
