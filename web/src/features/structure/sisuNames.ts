/**
 * Shared exact official-name comparison for a Sisu capture and a Sisu plan PDF.
 *
 * The extractor and the capture parser emit the same ligatures and whitespace runs the official
 * print and page markup carry, so both read one normalization owner here before an exact
 * Finnish-or-English name equality.
 */

/** Normalize extraction whitespace and ligatures for an exact official name comparison. */
export function normalizeSisuName(name: string): string {
  return name
    .replaceAll("ﬁ", "fi")
    .replaceAll("ﬂ", "fl")
    .replace(/\s+/g, " ")
    .trim();
}

/** Return whether one official name equals the extracted name after extraction normalization. */
export function sameOfficialName(
  module: { name_fi: string | null; name_en: string | null },
  name: string,
): boolean {
  const wanted = normalizeSisuName(name);
  return [module.name_fi, module.name_en].some(
    (candidate) =>
      candidate !== null && normalizeSisuName(candidate) === wanted,
  );
}
