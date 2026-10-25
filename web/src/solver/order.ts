/** Compare the ordered keys the route solver sorts and ties on. */

/** One value in a lexicographic key: a number, a string, or a nested key. */
export type KeyPart = number | string | readonly KeyPart[];

/** Compare two text values by their JavaScript code-unit order. */
export function compareText(first: string, second: string): number {
  if (first === second) {
    return 0;
  }
  return first < second ? -1 : 1;
}

/**
 * Compare two lexicographic keys.
 *
 * Two numbers compare numerically and two strings compare with `<`. Two arrays compare element by
 * element and then by length. A number against a string, an array against a number or string, and
 * any other pairing throw.
 */
export function compareKey(first: KeyPart, second: KeyPart): number {
  const firstIsArray = Array.isArray(first);
  const secondIsArray = Array.isArray(second);
  if (firstIsArray || secondIsArray) {
    if (!firstIsArray || !secondIsArray) {
      throw new Error("cannot compare a key array with a scalar key");
    }
    const length = Math.min(first.length, second.length);
    for (let index = 0; index < length; index += 1) {
      const result = compareKey(first[index], second[index]);
      if (result !== 0) {
        return result;
      }
    }
    if (first.length === second.length) {
      return 0;
    }
    return first.length < second.length ? -1 : 1;
  }
  if (typeof first === "string" || typeof second === "string") {
    if (typeof first !== "string" || typeof second !== "string") {
      throw new Error("cannot compare a number key with a string key");
    }
    return compareText(first, second);
  }
  if (first === second) {
    return 0;
  }
  return first < second ? -1 : 1;
}
