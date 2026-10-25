/** One zero-suppressed family core over subsets of orderable variables. */

/** One variable order: a comparator and one stable map key per variable. */
export type VariableOrder<V> = {
  /** Return a negative number when `a` sorts before `b`, a positive number after it. */
  compare(a: V, b: V): number;
  /** Return one stable string key for a variable. */
  key(variable: V): string;
};

/**
 * One transient zero-suppressed decision DAG over subsets of orderable variables.
 *
 * Handle 0 is the empty family and handle 1 holds exactly the empty subset. Node `n` lives at
 * `nodes[n - 2]`. Handles and the operation memos belong to one owner and never outlive it.
 */
export class Families<V> {
  static readonly ZERO = 0;
  static readonly ONE = 1;

  readonly nodes: [V, number, number][] = [];
  readonly unique = new Map<string, number>();
  readonly unionMemo = new Map<string, number>();
  readonly joinMemo = new Map<string, number>();

  constructor(private readonly order: VariableOrder<V>) {}

  /** Return the family holding exactly the one subset of the given variables. */
  singleton(variables: Iterable<V>): number {
    let handle = Families.ONE;
    for (const variable of [...variables].sort((a, b) =>
      this.order.compare(b, a),
    )) {
      handle = this.make(variable, Families.ZERO, handle);
    }
    return handle;
  }

  /** Return the set union of two families. */
  union(first: number, second: number): number {
    if (first === Families.ZERO) {
      return second;
    }
    if (second === Families.ZERO) {
      return first;
    }
    if (first === second) {
      return first;
    }
    const key = first < second ? `${first}|${second}` : `${second}|${first}`;
    const cached = this.unionMemo.get(key);
    if (cached !== undefined) {
      return cached;
    }
    const variable = this.top(first, second);
    const [firstLow, firstHigh] = this.split(first, variable);
    const [secondLow, secondHigh] = this.split(second, variable);
    const result = this.make(
      variable,
      this.union(firstLow, secondLow),
      this.union(firstHigh, secondHigh),
    );
    this.unionMemo.set(key, result);
    return result;
  }

  /** Return the union-product: one subset from each family, unioned. */
  join(first: number, second: number): number {
    if (first === Families.ZERO || second === Families.ZERO) {
      return Families.ZERO;
    }
    if (first === Families.ONE) {
      return second;
    }
    if (second === Families.ONE) {
      return first;
    }
    const key = first < second ? `${first}|${second}` : `${second}|${first}`;
    const cached = this.joinMemo.get(key);
    if (cached !== undefined) {
      return cached;
    }
    const variable = this.top(first, second);
    const [firstLow, firstHigh] = this.split(first, variable);
    const [secondLow, secondHigh] = this.split(second, variable);
    const high = this.union(
      this.union(
        this.join(firstHigh, secondLow),
        this.join(firstLow, secondHigh),
      ),
      this.join(firstHigh, secondHigh),
    );
    const result = this.make(variable, this.join(firstLow, secondLow), high);
    this.joinMemo.set(key, result);
    return result;
  }

  /**
   * Return the subfamily whose subset weights fall inside the inclusive bounds.
   *
   * `upper` of `null` leaves the upper bound open. Weights are integers.
   */
  filter(
    family: number,
    options: {
      weight(variable: V): number;
      lower: number;
      upper: number | null;
    },
  ): number {
    const ranges = new Map<number, [number, number] | null>();
    const variableWeights = new Map<string, number>();

    const suffixRange = (handle: number): [number, number] | null => {
      if (handle === Families.ZERO) {
        return null;
      }
      if (handle === Families.ONE) {
        return [0, 0];
      }
      const known = ranges.get(handle);
      if (known !== undefined) {
        return known;
      }
      const [variable, low, high] = this.nodes[handle - 2];
      const variableKey = this.order.key(variable);
      let variableWeight = variableWeights.get(variableKey);
      if (variableWeight === undefined) {
        variableWeight = options.weight(variable);
        variableWeights.set(variableKey, variableWeight);
      }
      const lowRange = suffixRange(low);
      const rawHighRange = suffixRange(high);
      const highRange =
        rawHighRange === null
          ? null
          : ([
              rawHighRange[0] + variableWeight,
              rawHighRange[1] + variableWeight,
            ] as [number, number]);
      const available: [number, number][] = [];
      if (lowRange !== null) {
        available.push(lowRange);
      }
      if (highRange !== null) {
        available.push(highRange);
      }
      if (available.length === 0) {
        ranges.set(handle, null);
        return null;
      }
      let minimum = available[0][0];
      let maximum = available[0][1];
      for (const value of available) {
        minimum = Math.min(minimum, value[0]);
        maximum = Math.max(maximum, value[1]);
      }
      const result: [number, number] = [minimum, maximum];
      ranges.set(handle, result);
      return result;
    };

    suffixRange(family);
    const memo = new Map<string, number>();

    const keep = (
      handle: number,
      remainingLower: number,
      remainingUpper: number | null,
    ): number => {
      if (remainingUpper !== null && remainingUpper < 0) {
        return Families.ZERO;
      }
      if (handle === Families.ZERO) {
        return Families.ZERO;
      }
      if (handle === Families.ONE) {
        return remainingLower > 0 ? Families.ZERO : Families.ONE;
      }
      const achievable = ranges.get(handle);
      if (achievable === undefined) {
        throw new Error(`family handle ${handle} has no suffix range`);
      }
      if (achievable === null) {
        return Families.ZERO;
      }
      if (
        achievable[1] < remainingLower ||
        (remainingUpper !== null && achievable[0] > remainingUpper)
      ) {
        return Families.ZERO;
      }
      if (
        achievable[0] >= remainingLower &&
        (remainingUpper === null || achievable[1] <= remainingUpper)
      ) {
        return handle;
      }
      const key = `${handle}|${remainingLower}|${remainingUpper}`;
      const cached = memo.get(key);
      if (cached !== undefined) {
        return cached;
      }
      const [variable, low, high] = this.nodes[handle - 2];
      const variableWeight = variableWeights.get(this.order.key(variable));
      if (variableWeight === undefined) {
        throw new Error(`variable ${this.order.key(variable)} has no weight`);
      }
      const nextLower = Math.max(remainingLower - variableWeight, 0);
      const nextUpper =
        remainingUpper === null ? null : remainingUpper - variableWeight;
      const result = this.make(
        variable,
        keep(low, remainingLower, remainingUpper),
        keep(high, nextLower, nextUpper),
      );
      memo.set(key, result);
      return result;
    };

    return keep(family, options.lower, options.upper);
  }

  /**
   * Split a family into members without, and members with, any predicate variable.
   *
   * The first result holds the members containing no predicate variable. The second holds the
   * members containing at least one.
   */
  splitByPredicate(
    family: number,
    predicate: (variable: V) => boolean,
  ): [number, number] {
    const memo = new Map<number, [number, number]>();

    const visit = (handle: number): [number, number] => {
      if (handle === Families.ZERO) {
        return [Families.ZERO, Families.ZERO];
      }
      if (handle === Families.ONE) {
        return [Families.ONE, Families.ZERO];
      }
      const cached = memo.get(handle);
      if (cached !== undefined) {
        return cached;
      }
      const [variable, low, high] = this.nodes[handle - 2];
      const [lowWithout, lowWith] = visit(low);
      const [highWithout, highWith] = visit(high);
      let without: number;
      let withPredicate: number;
      if (predicate(variable)) {
        without = lowWithout;
        withPredicate = this.union(highWithout, this.union(highWith, lowWith));
      } else {
        without = this.make(variable, lowWithout, highWithout);
        withPredicate = this.make(variable, lowWith, highWith);
      }
      const result: [number, number] = [without, withPredicate];
      memo.set(handle, result);
      return result;
    };

    return visit(family);
  }

  /** Return the family of subsets with every predicate variable existentially removed. */
  project(family: number, predicate: (variable: V) => boolean): number {
    const memo = new Map<number, number>();

    const drop = (handle: number): number => {
      if (handle === Families.ZERO) {
        return Families.ZERO;
      }
      if (handle === Families.ONE) {
        return Families.ONE;
      }
      const cached = memo.get(handle);
      if (cached !== undefined) {
        return cached;
      }
      const [variable, low, high] = this.nodes[handle - 2];
      const result = predicate(variable)
        ? this.union(drop(low), drop(high))
        : this.make(variable, drop(low), drop(high));
      memo.set(handle, result);
      return result;
    };

    return drop(family);
  }

  /**
   * Return the exact set-family intersection.
   *
   * A `ZERO` operand kills the result and equal handles intersect to themselves.
   */
  intersection(first: number, second: number): number {
    const memo = new Map<string, number>();

    const visit = (left: number, right: number): number => {
      if (left === Families.ZERO || right === Families.ZERO) {
        return Families.ZERO;
      }
      if (left === right) {
        return left;
      }
      const key = left < right ? `${left}|${right}` : `${right}|${left}`;
      const cached = memo.get(key);
      if (cached !== undefined) {
        return cached;
      }
      const variable = this.top(left, right);
      const [leftLow, leftHigh] = this.split(left, variable);
      const [rightLow, rightHigh] = this.split(right, variable);
      const result = this.make(
        variable,
        visit(leftLow, rightLow),
        visit(leftHigh, rightHigh),
      );
      memo.set(key, result);
      return result;
    };

    return visit(first, second);
  }

  /**
   * Return the subfamily whose members have one variable present or absent as requested.
   *
   * An included member keeps the constrained variable.
   */
  restrictVariable(
    family: number,
    variable: V,
    options: { present: boolean },
  ): number {
    const memo = new Map<number, number>();

    const visit = (handle: number): number => {
      if (handle === Families.ZERO) {
        return Families.ZERO;
      }
      if (handle === Families.ONE) {
        return options.present ? Families.ZERO : Families.ONE;
      }
      const [nodeVariable, low, high] = this.nodes[handle - 2];
      const order = this.order.compare(nodeVariable, variable);
      if (order === 0) {
        return options.present ? this.make(variable, Families.ZERO, high) : low;
      }
      if (order > 0) {
        return options.present ? Families.ZERO : handle;
      }
      const cached = memo.get(handle);
      if (cached !== undefined) {
        return cached;
      }
      const result = this.make(nodeVariable, visit(low), visit(high));
      memo.set(handle, result);
      return result;
    };

    return visit(family);
  }

  /**
   * Return the exact union-product join preimage of two families against an allowed family.
   *
   * The first result holds the `first` members whose union with some `second` member is allowed,
   * and the second holds the matching `second` members.
   */
  joinPreimage(
    first: number,
    second: number,
    allowed: number,
  ): [number, number] {
    const memo = new Map<string, [number, number]>();

    const visit = (
      left: number,
      right: number,
      target: number,
    ): [number, number] => {
      if (
        left === Families.ZERO ||
        right === Families.ZERO ||
        target === Families.ZERO
      ) {
        return [Families.ZERO, Families.ZERO];
      }
      if (
        left === Families.ONE &&
        right === Families.ONE &&
        target === Families.ONE
      ) {
        return [Families.ONE, Families.ONE];
      }
      const key = `${left}|${right}|${target}`;
      const cached = memo.get(key);
      if (cached !== undefined) {
        return cached;
      }
      let variable: V | undefined;
      for (const handle of [left, right, target]) {
        if (handle < 2) {
          continue;
        }
        const candidate = this.nodes[handle - 2][0];
        if (
          variable === undefined ||
          this.order.compare(candidate, variable) < 0
        ) {
          variable = candidate;
        }
      }
      if (variable === undefined) {
        throw new Error("join preimage has no non-terminal variable");
      }
      const [leftLow, leftHigh] = this.split(left, variable);
      const [rightLow, rightHigh] = this.split(right, variable);
      const [targetLow, targetHigh] = this.split(target, variable);
      const lowLow = visit(leftLow, rightLow, targetLow);
      const highLow = visit(leftHigh, rightLow, targetHigh);
      const lowHigh = visit(leftLow, rightHigh, targetHigh);
      const highHigh = visit(leftHigh, rightHigh, targetHigh);
      const result: [number, number] = [
        this.make(
          variable,
          this.union(lowLow[0], lowHigh[0]),
          this.union(highLow[0], highHigh[0]),
        ),
        this.make(
          variable,
          this.union(lowLow[1], highLow[1]),
          this.union(lowHigh[1], highHigh[1]),
        ),
      ];
      memo.set(key, result);
      return result;
    };

    return visit(first, second, allowed);
  }

  /**
   * Return the source members whose predicate-variable projection belongs to one allowed family.
   *
   * At a removed source variable both source branches are matched against the same allowed family.
   * At a retained variable the source and allowed branches match low to low and high to high.
   */
  projectPreimage(
    source: number,
    allowed: number,
    predicate: (variable: V) => boolean,
  ): number {
    const memo = new Map<string, number>();

    const visit = (sourceHandle: number, allowedHandle: number): number => {
      if (sourceHandle === Families.ZERO || allowedHandle === Families.ZERO) {
        return Families.ZERO;
      }
      if (sourceHandle === Families.ONE) {
        return this.contains(allowedHandle, []) ? Families.ONE : Families.ZERO;
      }
      const key = `${sourceHandle}|${allowedHandle}`;
      const cached = memo.get(key);
      if (cached !== undefined) {
        return cached;
      }
      const variable = this.top(sourceHandle, allowedHandle);
      const [sourceLow, sourceHigh] = this.split(sourceHandle, variable);
      const [allowedLow, allowedHigh] = this.split(allowedHandle, variable);
      const result = predicate(variable)
        ? this.make(
            variable,
            visit(sourceLow, allowedLow),
            visit(sourceHigh, allowedLow),
          )
        : this.make(
            variable,
            visit(sourceLow, allowedLow),
            visit(sourceHigh, allowedHigh),
          );
      memo.set(key, result);
      return result;
    };

    return visit(source, allowed);
  }

  /** Return whether one exact subset is a member of the family. */
  contains(family: number, member: Iterable<V>): boolean {
    const remaining = new Set<string>();
    for (const variable of member) {
      remaining.add(this.order.key(variable));
    }
    let handle = family;
    while (handle >= 2) {
      const [variable, low, high] = this.nodes[handle - 2];
      const key = this.order.key(variable);
      if (remaining.has(key)) {
        remaining.delete(key);
        handle = high;
      } else {
        handle = low;
      }
    }
    return handle === Families.ONE && remaining.size === 0;
  }

  /**
   * Return the greatest subset weight strictly below one budget, or `null` when none exists.
   *
   * `ONE` contributes zero only while the remaining budget is positive. The low branch keeps the
   * budget, and the high branch subtracts the variable's weight and adds it to the returned suffix.
   */
  maxWeightStrictlyBelow(
    family: number,
    options: { weight(variable: V): number; budget: number },
  ): number | null {
    const memo = new Map<string, number | null>();

    const visit = (handle: number, remaining: number): number | null => {
      if (handle === Families.ZERO) {
        return null;
      }
      if (handle === Families.ONE) {
        return remaining > 0 ? 0 : null;
      }
      const key = `${handle}|${remaining}`;
      if (memo.has(key)) {
        return memo.get(key) ?? null;
      }
      const [variable, low, high] = this.nodes[handle - 2];
      const variableWeight = options.weight(variable);
      const bestLow = visit(low, remaining);
      const suffix = visit(high, remaining - variableWeight);
      const bestHigh = suffix === null ? null : variableWeight + suffix;
      const result =
        bestLow === null
          ? bestHigh
          : bestHigh === null
            ? bestLow
            : bestLow >= bestHigh
              ? bestLow
              : bestHigh;
      memo.set(key, result);
      return result;
    };

    return visit(family, options.budget);
  }

  /** Return the family without its empty subset, if the empty subset is present. */
  removeEmpty(family: number): number {
    const memo = new Map<number, number>();

    const strip = (handle: number): number => {
      if (handle === Families.ZERO) {
        return Families.ZERO;
      }
      if (handle === Families.ONE) {
        return Families.ZERO;
      }
      const cached = memo.get(handle);
      if (cached !== undefined) {
        return cached;
      }
      const [variable, low, high] = this.nodes[handle - 2];
      const result = this.make(variable, strip(low), high);
      memo.set(handle, result);
      return result;
    };

    return strip(family);
  }

  /** Return one shared node handle, suppressing a zero high branch. */
  protected make(variable: V, low: number, high: number): number {
    if (high === Families.ZERO) {
      return low;
    }
    const key = `${this.order.key(variable)}|${low}|${high}`;
    const existing = this.unique.get(key);
    if (existing !== undefined) {
      return existing;
    }
    const handle = this.nodes.length + 2;
    this.nodes.push([variable, low, high]);
    this.unique.set(key, handle);
    return handle;
  }

  /** Return the smallest variable named by either non-terminal family. */
  private top(first: number, second: number): V {
    if (first < 2) {
      return this.nodes[second - 2][0];
    }
    if (second < 2) {
      return this.nodes[first - 2][0];
    }
    const firstVariable = this.nodes[first - 2][0];
    const secondVariable = this.nodes[second - 2][0];
    return this.order.compare(firstVariable, secondVariable) <= 0
      ? firstVariable
      : secondVariable;
  }

  /** Split one family into its exclude and include branches at one variable. */
  private split(handle: number, variable: V): [number, number] {
    if (handle < 2) {
      return [handle, Families.ZERO];
    }
    const [nodeVariable, low, high] = this.nodes[handle - 2];
    if (this.order.compare(nodeVariable, variable) === 0) {
      return [low, high];
    }
    return [handle, Families.ZERO];
  }
}
