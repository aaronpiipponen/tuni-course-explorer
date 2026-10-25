/** Parse decimal credit values into exact hundredths. */

/**
 * Return one decimal credit string as hundredths.
 *
 * Accepts a non-negative decimal with at most two significant decimal places, such as `"5"`,
 * `"5.00"` or `"2.5"`. Trailing zeros past the second decimal are ignored. Any other text, and
 * any nonzero digit past the second decimal, throws.
 */
export function parseCredits(text: string): number {
  const match = /^(\d+)(?:\.(\d*))?$/.exec(text);
  if (match === null) {
    throw new Error(`invalid credits ${text}`);
  }
  const fraction = (match[2] ?? "").padEnd(2, "0");
  if (
    fraction
      .slice(2)
      .split("")
      .some((digit) => digit !== "0")
  ) {
    throw new Error(`invalid credits ${text}`);
  }
  return Number(match[1]) * 100 + Number(fraction.slice(0, 2));
}

/**
 * Format hundredths as canonical compact decimal credit text.
 *
 * Zero renders as `"0"`, and trailing fraction zeros are removed, so `300` renders `"3"` and
 * `90` renders `"0.9"`. A negative or non-integer value throws.
 */
export function formatCredits(hundredths: number): string {
  if (!Number.isInteger(hundredths) || hundredths < 0) {
    throw new Error(`invalid credit hundredths ${hundredths}`);
  }
  if (hundredths === 0) {
    return "0";
  }
  const whole = Math.floor(hundredths / 100);
  const fraction = String(hundredths % 100)
    .padStart(2, "0")
    .replace(/0+$/, "");
  return fraction.length === 0 ? String(whole) : `${whole}.${fraction}`;
}
