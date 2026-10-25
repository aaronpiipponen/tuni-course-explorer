/** Tagged path families over course, opaque and attested identities with provenance traces. */
import type { VariableOrder } from "./families";
import { Families } from "./families";
import { MinHeap } from "./heap";
import { compareKey, compareText, type KeyPart } from "./order";
import {
  DrawingNodePool,
  firstJoinPair,
  firstProjectPreimage,
  type DrawingChild,
  type DrawingNode,
  type DrawingTraceRef,
} from "./route-derivation";

/** One typed identity kind: a canonical course, an opaque source block or a manual completion. */
export type PathKind = "course" | "opaque" | "attested";

/** One identity role: a measured witness support or the new-work cost support. */
export type PathRole = "witness" | "new";

/** One tagged path variable: rank, kind, identity and role. */
export type PathVariable = readonly [
  rank: number,
  kind: PathKind,
  identity: string,
  role: PathRole,
];

/** One typed occurrence label: kind, identity and the support it satisfies. */
export type PathLabel = readonly [
  kind: string,
  identity: string,
  support: string,
];

/** One support identity selected by the exact optimization key. */
export type BestSupport = {
  credits: number;
  inactiveNewCount: number;
  newCourseIds: string[];
  newOpaqueWorkIds: string[];
  witnessCourseIds: string[];
  witnessNonCourseIds: [string, string][];
};

/** Order tagged path variables by rank, kind, identity and role. */
export const pathOrder: VariableOrder<PathVariable> = {
  compare(first: PathVariable, second: PathVariable): number {
    if (first[0] !== second[0]) {
      return first[0] < second[0] ? -1 : 1;
    }
    for (const index of [1, 2, 3] as const) {
      const result = compareText(first[index], second[index]);
      if (result !== 0) {
        return result;
      }
    }
    return 0;
  },
  key(variable: PathVariable): string {
    return `${variable[0]}\u0000${variable[1]}\u0000${variable[2]}\u0000${variable[3]}`;
  },
};

/** Return one best support's tagged variables through its owner. */
export function bestSupportVariables(
  families: PathFamilies,
  support: BestSupport,
): PathVariable[] {
  const variables: PathVariable[] = [];
  for (const groupId of support.newCourseIds) {
    variables.push(families.newVariable(PathFamilies.COURSE, groupId));
  }
  for (const workKey of support.newOpaqueWorkIds) {
    variables.push(families.newVariable(PathFamilies.OPAQUE, workKey));
  }
  for (const groupId of support.witnessCourseIds) {
    variables.push(families.witnessVariable(PathFamilies.COURSE, groupId));
  }
  for (const [kind, identity] of support.witnessNonCourseIds) {
    variables.push(families.witnessVariable(kind as PathKind, identity));
  }
  return variables;
}

/** One provenance trace node. References point to earlier trace indices. */
type TraceNode = {
  support: number;
  operation: string;
  inputs: number[];
  label: PathLabel | null;
  drawingInputs: readonly DrawingTraceRef[];
};

/** One drawing fragment selected below one trace reference. */
type DrawingFragment =
  | { kind: "none" }
  | { kind: "node"; node: DrawingNode }
  | { kind: "children"; children: DrawingChild[] };

/** One attempt allocated beyond its configured family and provenance budget. */
export class PathSizeLimitExceeded extends Error {}

/** One transient family DAG of tagged path identities and operation provenance. */
export class PathFamilies extends Families<PathVariable> {
  static readonly COURSE = "course";
  static readonly OPAQUE = "opaque";
  static readonly ATTESTED = "attested";
  static readonly NODE = "node";
  static readonly WITNESS = "witness";
  static readonly NEW = "new";
  static readonly LEAF = "leaf";
  static readonly UNION = "union";
  static readonly JOIN = "join";
  static readonly IDENTITY = "identity";
  static readonly PROJECT = "project";

  private readonly credits: ReadonlyMap<string, number>;
  private readonly opaqueCredits: ReadonlyMap<string, number>;
  private readonly inactive: ReadonlySet<string>;
  private readonly maxCompactNodes: number | null;
  private readonly attestedCredits = new Map<string, number | null>();
  private readonly rank = new Map<string, number>();
  private readonly orderList: [PathKind, string][] = [];
  protected readonly traces: TraceNode[] = [];
  private readonly drawingPool = new DrawingNodePool();
  private readonly drawingMemo = new Map<string, DrawingFragment>();
  private readonly drawingReferenceIds = new WeakMap<object, number>();
  private drawingReferenceCounter = 0;

  constructor(
    creditsByGroupId: ReadonlyMap<string, number>,
    groupOrder: readonly (readonly [string, string])[],
    opaqueCreditsByWorkKey: ReadonlyMap<string, number>,
    inactiveGroupIds: ReadonlySet<string>,
    maxCompactNodes: number | null = null,
  ) {
    super(pathOrder);
    this.credits = creditsByGroupId;
    this.opaqueCredits = opaqueCreditsByWorkKey;
    this.inactive = inactiveGroupIds;
    this.maxCompactNodes = maxCompactNodes;
    for (const [kind, identity] of groupOrder) {
      this.register(kind as PathKind, identity);
    }
  }

  /** Return one shared node handle, failing once the attempt exceeds its budget. */
  protected override make(
    variable: PathVariable,
    low: number,
    high: number,
  ): number {
    const handle = super.make(variable, low, high);
    this.checkSize();
    return handle;
  }

  /** Throw once the allocated node and provenance count exceeds the configured limit. */
  private checkSize(): void {
    if (
      this.maxCompactNodes !== null &&
      this.nodes.length + this.traces.length > this.maxCompactNodes
    ) {
      throw new PathSizeLimitExceeded();
    }
  }

  /** Register one attested manual-completion identity and its known source extent. */
  registerAttested(actionKey: string, credits: number | null): void {
    this.attestedCredits.set(actionKey, credits);
    this.register(PathFamilies.ATTESTED, actionKey);
  }

  /** Return the tagged variable marking one identity as a witness. */
  witnessVariable(kind: PathKind, identity: string): PathVariable {
    return [this.rankOf(kind, identity), kind, identity, PathFamilies.WITNESS];
  }

  /** Return the tagged variable marking one identity as a new charge. */
  newVariable(kind: PathKind, identity: string): PathVariable {
    return [this.rankOf(kind, identity), kind, identity, PathFamilies.NEW];
  }

  /** Return whether one tagged variable is a witness support. */
  isWitness(variable: PathVariable): boolean {
    return variable[3] === PathFamilies.WITNESS;
  }

  /** Return one variable's credit weight: a known witness measure, else zero. */
  creditWeight(variable: PathVariable): number {
    if (variable[3] !== PathFamilies.WITNESS) {
      return 0;
    }
    const measure = this.measure(variable[1], variable[2]);
    if (measure === null) {
      throw new Error(
        "unknown-measure attested witness cannot be credit-weighted",
      );
    }
    return measure;
  }

  /** Return one variable's course-count weight: one for a real course witness, else zero. */
  countWeight(variable: PathVariable): number {
    if (
      variable[3] !== PathFamilies.WITNESS ||
      variable[1] !== PathFamilies.COURSE
    ) {
      return 0;
    }
    return 1;
  }

  /** Return one variable's new-work credit weight: a known measure for NEW, else zero. */
  newCreditWeight(variable: PathVariable): number {
    if (variable[3] !== PathFamilies.NEW) {
      return 0;
    }
    const measure = this.measure(variable[1], variable[2]);
    return measure === null ? 0 : measure;
  }

  /** Return whether one witness variable has no known source credit extent. */
  isUnknownCredit(variable: PathVariable): boolean {
    return (
      variable[3] === PathFamilies.WITNESS &&
      variable[1] === PathFamilies.ATTESTED &&
      (this.attestedCredits.get(variable[2]) ?? null) === null
    );
  }

  /** Return one variable's inactive-new-course weight: one for an inactive new course, else zero. */
  inactiveNewWeight(variable: PathVariable): number {
    if (
      variable[3] !== PathFamilies.NEW ||
      variable[1] !== PathFamilies.COURSE
    ) {
      return 0;
    }
    return this.inactive.has(variable[2]) ? 1 : 0;
  }

  /** Return whether one witness variable is not a real counted course. */
  isUnknownCount(variable: PathVariable): boolean {
    return (
      variable[3] === PathFamilies.WITNESS &&
      variable[1] !== PathFamilies.COURSE
    );
  }

  /** Record one leaf node holding a typed support label or a neutral identity. */
  leafTrace(support: number, label: PathLabel | null = null): number {
    return this.addTrace(support, PathFamilies.LEAF, [], label);
  }

  /** Record one union of two provenance nodes into the resulting support. */
  unionTrace(
    support: number,
    first: number,
    second: number,
    drawingInputs: readonly [DrawingTraceRef, DrawingTraceRef] = [
      { kind: "trace", trace: first },
      { kind: "trace", trace: second },
    ],
  ): number {
    return this.addTrace(
      support,
      PathFamilies.UNION,
      [first, second],
      null,
      drawingInputs,
    );
  }

  /** Record one union-product join of two provenance nodes into the resulting support. */
  joinTrace(
    support: number,
    first: number,
    second: number,
    drawingInputs: readonly [DrawingTraceRef, DrawingTraceRef] = [
      { kind: "trace", trace: first },
      { kind: "trace", trace: second },
    ],
  ): number {
    return this.addTrace(
      support,
      PathFamilies.JOIN,
      [first, second],
      null,
      drawingInputs,
    );
  }

  /** Record one support-only identity restriction over an earlier provenance node. */
  identityTrace(
    support: number,
    source: number,
    drawingInput: DrawingTraceRef = { kind: "trace", trace: source },
  ): number {
    return this.addTrace(support, PathFamilies.IDENTITY, [source], null, [
      drawingInput,
    ]);
  }

  /** Record one existential witness projection over an earlier provenance node. */
  projectTrace(
    support: number,
    source: number,
    drawingInput: DrawingTraceRef = { kind: "trace", trace: source },
  ): number {
    return this.addTrace(support, PathFamilies.PROJECT, [source], null, [
      drawingInput,
    ]);
  }

  /**
   * Return the one drawing node selected for a route partition's member.
   *
   * The reference records the winning derivation's native node boundaries and child slots. Equal
   * occurrences share one interned node within the calculation, and the walk reads family handles
   * only.
   */
  reconstructDrawing(
    reference: DrawingTraceRef,
    member: ReadonlySet<PathVariable>,
  ): DrawingNode {
    const fragment = this.selectDrawing(
      reference,
      this.orderedDrawingMember(member),
    );
    if (fragment.kind !== "node") {
      throw new Error("the chosen route has no outermost drawing node");
    }
    return fragment.node;
  }

  /** Return one drawing member as unique path variables in path order. */
  private orderedDrawingMember(
    member: ReadonlySet<PathVariable>,
  ): PathVariable[] {
    const unique = new Map<string, PathVariable>();
    for (const variable of member) {
      unique.set(pathOrder.key(variable), variable);
    }
    return [...unique.values()].sort((first, second) =>
      pathOrder.compare(first, second),
    );
  }

  /** Return one stable local id for a drawing reference object. */
  private drawingReferenceId(reference: DrawingTraceRef): number {
    const existing = this.drawingReferenceIds.get(reference);
    if (existing !== undefined) {
      return existing;
    }
    this.drawingReferenceCounter += 1;
    this.drawingReferenceIds.set(reference, this.drawingReferenceCounter);
    return this.drawingReferenceCounter;
  }

  /**
   * Return the drawing fragment one reference selects for a unique member in path order.
   *
   * The fragment is memoized by reference identity and the ordered member keys, including neutral
   * and child-slot fragments. A cached fragment is shared and read-only, and a selection that
   * throws is not cached.
   */
  private selectDrawing(
    reference: DrawingTraceRef,
    member: readonly PathVariable[],
  ): DrawingFragment {
    const key = `${this.drawingReferenceId(reference)}|${JSON.stringify(
      member.map((variable) => pathOrder.key(variable)),
    )}`;
    const cached = this.drawingMemo.get(key);
    if (cached !== undefined) {
      return cached;
    }
    const fragment = this.selectDrawingUncached(reference, member);
    this.drawingMemo.set(key, fragment);
    return fragment;
  }

  /** Return the drawing fragment one reference selects, evaluated without the fragment memo. */
  private selectDrawingUncached(
    reference: DrawingTraceRef,
    member: readonly PathVariable[],
  ): DrawingFragment {
    if (reference.kind === "node") {
      const inner = this.selectDrawing(reference.input, member);
      if (inner.kind === "node") {
        throw new Error(
          "a native drawing node is wrapped without a child slot",
        );
      }
      return {
        kind: "node",
        node: this.drawingPool.node(
          reference.ownerGroupId,
          reference.pieceId,
          inner.kind === "children" ? inner.children : [],
        ),
      };
    }
    if (reference.kind === "slot") {
      const inner = this.selectDrawing(reference.input, member);
      if (inner.kind === "none") {
        return { kind: "children", children: [] };
      }
      if (inner.kind === "children") {
        throw new Error("a drawing slot wraps child slots instead of a node");
      }
      return {
        kind: "children",
        children: [{ slot: reference.slot, node: inner.node }],
      };
    }
    const trace = this.traces[reference.trace];
    if (trace === undefined) {
      throw new Error(`unknown path trace ${reference.trace}`);
    }
    if (trace.operation === PathFamilies.LEAF) {
      return { kind: "none" };
    }
    if (trace.operation === PathFamilies.UNION) {
      const index = trace.inputs.findIndex((input) => {
        const inputTrace = this.traces[input];
        if (inputTrace === undefined) {
          throw new Error(`unknown path trace ${input}`);
        }
        return this.contains(inputTrace.support, member);
      });
      const input = index < 0 ? undefined : trace.drawingInputs[index];
      if (input === undefined) {
        throw new Error("a union drawing has no feasible input");
      }
      return this.selectDrawing(input, member);
    }
    if (trace.operation === PathFamilies.IDENTITY) {
      const input = trace.drawingInputs[0];
      if (input === undefined) {
        throw new Error("an identity drawing has no input");
      }
      return this.selectDrawing(input, member);
    }
    if (trace.operation === PathFamilies.JOIN) {
      const [firstInput, secondInput] = trace.inputs.map(
        (input) => this.traces[input],
      );
      if (firstInput === undefined || secondInput === undefined) {
        throw new Error("a join drawing has an unknown input");
      }
      const pair = firstJoinPair(
        this.nodes,
        pathOrder,
        firstInput.support,
        secondInput.support,
        member,
      );
      if (pair === null) {
        throw new Error("a join drawing has no feasible preimage pair");
      }
      const firstReference = trace.drawingInputs[0];
      const secondReference = trace.drawingInputs[1];
      if (firstReference === undefined || secondReference === undefined) {
        throw new Error("a join drawing has no input reference");
      }
      const first = this.selectDrawing(firstReference, pair[0]);
      const second = this.selectDrawing(secondReference, pair[1]);
      return mergeDrawingFragments(first, second);
    }
    if (trace.operation === PathFamilies.PROJECT) {
      const input = trace.inputs[0];
      const inputTrace = this.traces[input];
      if (inputTrace === undefined) {
        throw new Error(`unknown path trace ${input}`);
      }
      const restored = firstProjectPreimage(
        this.nodes,
        pathOrder,
        inputTrace.support,
        member,
        (variable) => this.isWitness(variable),
      );
      const inputReference = trace.drawingInputs[0];
      if (restored === null || inputReference === undefined) {
        throw new Error("a projection drawing has no feasible preimage");
      }
      return this.selectDrawing(inputReference, restored);
    }
    throw new Error(`unknown path trace operation ${trace.operation}`);
  }

  /**
   * Return the least new-course credit total over a support family, or `null` when empty.
   *
   * The low branch keeps the running total and the high branch adds a variable's source measure
   * only when it is a NEW support.
   */
  minimumNewCredits(family: number): number | null {
    const memo = new Map<number, number | null>();

    const visit = (handle: number): number | null => {
      if (handle === Families.ZERO) {
        return null;
      }
      if (handle === Families.ONE) {
        return 0;
      }
      if (memo.has(handle)) {
        const cached = memo.get(handle);
        return cached === undefined ? null : cached;
      }
      const [variable, low, high] = this.nodes[handle - 2];
      const bestLow = visit(low);
      const suffix = visit(high);
      let bestHigh: number | null;
      if (suffix === null) {
        bestHigh = null;
      } else {
        const measure =
          variable[3] === PathFamilies.NEW
            ? this.measure(variable[1], variable[2])
            : null;
        bestHigh = suffix + (measure === null ? 0 : measure);
      }
      const result =
        bestLow === null
          ? bestHigh
          : bestHigh === null
            ? bestLow
            : bestLow <= bestHigh
              ? bestLow
              : bestHigh;
      memo.set(handle, result);
      return result;
    };

    return visit(family);
  }

  /**
   * Return the least inactive-new-course count over a support family, or `null` when empty.
   *
   * The fold uses the same zero-suppressed walk as the credit bound.
   */
  minimumInactiveNewCount(family: number): number | null {
    const memo = new Map<number, number | null>();

    const visit = (handle: number): number | null => {
      if (handle === Families.ZERO) {
        return null;
      }
      if (handle === Families.ONE) {
        return 0;
      }
      if (memo.has(handle)) {
        const cached = memo.get(handle);
        return cached === undefined ? null : cached;
      }
      const [variable, low, high] = this.nodes[handle - 2];
      const suffix = visit(high);
      const bestLow = visit(low);
      const bestHigh =
        suffix === null ? null : suffix + this.inactiveNewWeight(variable);
      const result =
        bestLow === null
          ? bestHigh
          : bestHigh === null
            ? bestLow
            : bestLow <= bestHigh
              ? bestLow
              : bestHigh;
      memo.set(handle, result);
      return result;
    };

    return visit(family);
  }

  /**
   * Return the member minimizing new credits, then fewest inactive new courses, then typed ties.
   *
   * The minimum new-credit total is found by one exact fold, then the same fold restricts to the
   * fewest inactive canonical new courses. The filtered family is successively restricted to the
   * exact opaque, course and witness coordinates selected by projected prefix walks.
   */
  bestSupport(family: number): BestSupport | null {
    if (family === Families.ZERO) {
      return null;
    }
    const singletonVariables: PathVariable[] = [];
    let handle = family;
    while (handle >= 2) {
      const [variable, low, high] = this.nodes[handle - 2];
      if (low !== Families.ZERO) {
        break;
      }
      singletonVariables.push(variable);
      handle = high;
    }
    if (handle === Families.ONE) {
      let credits = 0;
      for (const variable of singletonVariables) {
        if (variable[3] === PathFamilies.NEW) {
          credits += this.measure(variable[1], variable[2]) ?? 0;
        }
      }
      let inactiveNewCount = 0;
      for (const variable of singletonVariables) {
        inactiveNewCount += this.inactiveNewWeight(variable);
      }
      const newCourseIds: string[] = [];
      const newOpaqueWorkIds: string[] = [];
      const witnessCourseIds: string[] = [];
      const witnessNonCourse: [string, string][] = [];
      for (const [kind, identity, role] of singletonVariables.map(
        (variable) => [variable[1], variable[2], variable[3]] as const,
      )) {
        if (role === PathFamilies.NEW && kind === PathFamilies.COURSE) {
          newCourseIds.push(identity);
        } else if (role === PathFamilies.NEW && kind === PathFamilies.OPAQUE) {
          newOpaqueWorkIds.push(identity);
        } else if (
          role === PathFamilies.WITNESS &&
          kind === PathFamilies.COURSE
        ) {
          witnessCourseIds.push(identity);
        } else if (role === PathFamilies.WITNESS) {
          witnessNonCourse.push([kind, identity]);
        }
      }
      newCourseIds.sort(compareText);
      newOpaqueWorkIds.sort(compareText);
      witnessCourseIds.sort(compareText);
      witnessNonCourse.sort((first, second) => compareKey(first, second));
      return {
        credits,
        inactiveNewCount,
        newCourseIds,
        newOpaqueWorkIds,
        witnessCourseIds,
        witnessNonCourseIds: witnessNonCourse,
      };
    }
    const credits = this.minimumNewCredits(family);
    if (credits === null) {
      return null;
    }
    const costFiltered = this.filter(family, {
      weight: (variable) => this.newCreditWeight(variable),
      lower: credits,
      upper: credits,
    });
    const inactiveNewCount = this.minimumInactiveNewCount(costFiltered);
    if (inactiveNewCount === null) {
      return null;
    }
    let restricted = this.filter(costFiltered, {
      weight: (variable) => this.inactiveNewWeight(variable),
      lower: inactiveNewCount,
      upper: inactiveNewCount,
    });
    const newOpaqueIds = this.leastIdentities(restricted, PathFamilies.NEW, [
      PathFamilies.OPAQUE,
    ]).map(([, identity]) => identity);
    restricted = this.restrictKind(
      restricted,
      PathFamilies.NEW,
      PathFamilies.OPAQUE,
      newOpaqueIds,
    );
    const newCourseIds = this.leastIdentities(restricted, PathFamilies.NEW, [
      PathFamilies.COURSE,
    ]).map(([, identity]) => identity);
    restricted = this.restrictKind(
      restricted,
      PathFamilies.NEW,
      PathFamilies.COURSE,
      newCourseIds,
    );
    const witnessCourseIds = this.leastIdentities(
      restricted,
      PathFamilies.WITNESS,
      [PathFamilies.COURSE],
    ).map(([, identity]) => identity);
    restricted = this.restrictKind(
      restricted,
      PathFamilies.WITNESS,
      PathFamilies.COURSE,
      witnessCourseIds,
    );
    const witnessNonCourseIds = this.leastIdentities(
      restricted,
      PathFamilies.WITNESS,
      [PathFamilies.ATTESTED, PathFamilies.OPAQUE],
    );
    return {
      credits,
      inactiveNewCount,
      newCourseIds,
      newOpaqueWorkIds: newOpaqueIds,
      witnessCourseIds,
      witnessNonCourseIds,
    };
  }

  /**
   * Return every typed occurrence label present in any valid derivation of one member.
   *
   * Reachable provenance nodes are visited in descending creation order. The allowed family at a
   * node is intersected with the node's output support and propagated through the exact inverse of
   * the operation that produced it.
   */
  reconstructEvidence(
    trace: number,
    member: ReadonlySet<PathVariable>,
  ): PathLabel[] {
    const allowed = new Map<number, number>();
    allowed.set(trace, this.singleton(member));
    const pending = new MinHeap<number>((first, second) => second - first);
    pending.push(trace);
    const processed = new Set<number>();
    const labels = new Map<string, PathLabel>();
    while (pending.size > 0) {
      const index = pending.pop();
      if (processed.has(index)) {
        continue;
      }
      processed.add(index);
      const nodeAllowed = allowed.get(index);
      if (nodeAllowed === undefined) {
        continue;
      }
      const node = this.traces[index];
      if (node === undefined) {
        throw new Error(`unknown path trace ${index}`);
      }
      const constrained = this.intersection(nodeAllowed, node.support);
      if (constrained === Families.ZERO) {
        continue;
      }
      if (node.operation === PathFamilies.LEAF) {
        if (node.label !== null) {
          const key = `${node.label[0]}\u0000${node.label[1]}\u0000${node.label[2]}`;
          labels.set(key, node.label);
        }
      } else if (node.operation === PathFamilies.UNION) {
        for (const inputIndex of node.inputs) {
          const input = this.traces[inputIndex];
          if (input === undefined) {
            throw new Error(`unknown path trace ${inputIndex}`);
          }
          this.accumulateAllowed(
            allowed,
            pending,
            inputIndex,
            this.intersection(constrained, input.support),
          );
        }
      } else if (node.operation === PathFamilies.IDENTITY) {
        this.accumulateAllowed(allowed, pending, node.inputs[0], constrained);
      } else if (node.operation === PathFamilies.JOIN) {
        const [first, second] = node.inputs;
        const firstInput = this.traces[first];
        const secondInput = this.traces[second];
        if (firstInput === undefined || secondInput === undefined) {
          throw new Error("join trace references an unknown input");
        }
        const [firstAllowed, secondAllowed] = this.joinPreimage(
          firstInput.support,
          secondInput.support,
          constrained,
        );
        this.accumulateAllowed(allowed, pending, first, firstAllowed);
        this.accumulateAllowed(allowed, pending, second, secondAllowed);
      } else if (node.operation === PathFamilies.PROJECT) {
        const inputIndex = node.inputs[0];
        const input = this.traces[inputIndex];
        if (input === undefined) {
          throw new Error("project trace references an unknown input");
        }
        this.accumulateAllowed(
          allowed,
          pending,
          inputIndex,
          this.projectPreimage(input.support, constrained, (variable) =>
            this.isWitness(variable),
          ),
        );
      } else {
        throw new Error(`unknown path trace operation ${node.operation}`);
      }
    }
    return [...labels.values()];
  }

  /** Union one incoming allowed family onto a provenance node and schedule it. */
  private accumulateAllowed(
    allowed: Map<number, number>,
    pending: MinHeap<number>,
    index: number,
    family: number,
  ): void {
    if (family === Families.ZERO) {
      return;
    }
    const existing = allowed.get(index);
    if (existing === undefined) {
      allowed.set(index, family);
    } else {
      const merged = this.union(existing, family);
      if (merged === existing) {
        return;
      }
      allowed.set(index, merged);
    }
    pending.push(index);
  }

  /** Register one identity's stable internal rank, creating it once. */
  private register(kind: PathKind, identity: string): number {
    const key = `${kind}\u0000${identity}`;
    const existing = this.rank.get(key);
    if (existing !== undefined) {
      return existing;
    }
    const rank = this.orderList.length;
    this.rank.set(key, rank);
    this.orderList.push([kind, identity]);
    return rank;
  }

  /** Return one identity's registered rank, never a fabricated default. */
  private rankOf(kind: PathKind, identity: string): number {
    const rank = this.rank.get(`${kind}\u0000${identity}`);
    if (rank === undefined) {
      throw new Error(
        `${kind} identity ${identity} has no registered path rank`,
      );
    }
    return rank;
  }

  /** Return one identity's source minimum-credit measure, or `null` when unknown. */
  private measure(kind: PathKind, identity: string): number | null {
    if (kind === PathFamilies.OPAQUE) {
      return this.opaqueCredits.get(identity) ?? 0;
    }
    if (kind === PathFamilies.ATTESTED) {
      return this.attestedCredits.get(identity) ?? null;
    }
    return this.credits.get(identity) ?? 0;
  }

  /** Append one provenance node and return its index. */
  private addTrace(
    support: number,
    operation: string,
    inputs: number[],
    label: PathLabel | null = null,
    drawingInputs?: readonly DrawingTraceRef[],
  ): number {
    this.traces.push({
      support,
      operation,
      inputs,
      label,
      drawingInputs:
        drawingInputs ??
        inputs.map((input) => ({ kind: "trace", trace: input })),
    });
    this.checkSize();
    return this.traces.length - 1;
  }

  /** Restrict a family to exactly one kind's selected identities and no others of that kind. */
  private restrictKind(
    family: number,
    role: PathRole,
    kind: PathKind,
    selected: readonly string[],
  ): number {
    const chosen = new Set(selected);
    let restricted = family;
    for (const [candidateKind, identity] of this.orderList) {
      if (candidateKind !== kind) {
        continue;
      }
      restricted = this.restrictVariable(
        restricted,
        this.variable(role, kind, identity),
        { present: chosen.has(identity) },
      );
    }
    return restricted;
  }

  /** Return one tagged variable for a known kind, identity and role. */
  private variable(
    role: PathRole,
    kind: PathKind,
    identity: string,
  ): PathVariable {
    return [this.rankOf(kind, identity), kind, identity, role];
  }

  /**
   * Return the lexicographically least sorted identity tuple of one kind and role.
   *
   * Identities are scanned in ascending canonical order, independent of the DAG variable order. The
   * walk projects away every other role and kind, then keeps a feasible subfamily and a selected
   * prefix.
   */
  private leastIdentities(
    family: number,
    role: PathRole,
    kinds: readonly PathKind[],
  ): [PathKind, string][] {
    const projected = this.project(
      family,
      (variable) => variable[3] !== role || !kinds.includes(variable[1]),
    );
    const identities = new Map<string, [PathKind, string]>();
    const pending = [projected];
    const visited = new Set<number>();
    while (pending.length > 0) {
      const handle = pending.pop();
      if (handle === undefined || handle < 2 || visited.has(handle)) {
        continue;
      }
      visited.add(handle);
      const [variable, low, high] = this.nodes[handle - 2];
      if (variable[3] === role && kinds.includes(variable[1])) {
        identities.set(`${variable[1]}\u0000${variable[2]}`, [
          variable[1],
          variable[2],
        ]);
      }
      pending.push(low, high);
    }
    const ordered = [...identities.values()].sort((first, second) =>
      compareKey(first, second),
    );
    if (ordered.length === 0) {
      return [];
    }
    const prefix: [PathKind, string][] = [];
    let feasible = projected;
    let position = 0;
    for (;;) {
      const member = prefix.map(([kind, identity]) =>
        this.variable(role, kind, identity),
      );
      if (this.contains(feasible, member)) {
        return prefix;
      }
      let advanced = false;
      while (position < ordered.length) {
        const [kind, identity] = ordered[position];
        position += 1;
        const included = this.restrictVariable(
          feasible,
          this.variable(role, kind, identity),
          { present: true },
        );
        if (included !== Families.ZERO) {
          feasible = included;
          prefix.push([kind, identity]);
          advanced = true;
          break;
        }
      }
      if (!advanced) {
        return prefix;
      }
    }
  }
}

/** Merge two selected fragments from one union or join into one fragment. */
function mergeDrawingFragments(
  first: DrawingFragment,
  second: DrawingFragment,
): DrawingFragment {
  if (first.kind === "none") {
    return second;
  }
  if (second.kind === "none") {
    return first;
  }
  if (first.kind === "children" && second.kind === "children") {
    return {
      kind: "children",
      children: [...first.children, ...second.children],
    };
  }
  throw new Error("two native drawing nodes are selected without child slots");
}

/** Return the exact support optimization key in the public typed tie order. */
export function supportKey(support: BestSupport): KeyPart[] {
  return [
    support.credits,
    support.inactiveNewCount,
    support.newOpaqueWorkIds,
    support.newCourseIds,
    support.witnessCourseIds,
    support.witnessNonCourseIds,
  ];
}
