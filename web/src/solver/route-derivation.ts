/** Request-local drawing derivation over one chosen route occurrence and its native slots. */
import type { VariableOrder } from "./families";

/** One native child slot and the drawing node selected for it. */
export type DrawingChild = { slot: number; node: DrawingNode };

/** One selected native drawing node, its owner identity and its ordered child slots. */
export type DrawingNode = {
  id: number;
  ownerGroupId: string;
  pieceId: string;
  children: readonly DrawingChild[];
};

/**
 * One drawing annotation on an operation trace.
 *
 * A plain trace reads the same trace node the evidence walk reads. A node reference wraps the
 * child slots selected below it into one semantic node, and a slot reference places one semantic
 * node in its native child slot.
 */
export type DrawingTraceRef =
  | { kind: "trace"; trace: number }
  | {
      kind: "node";
      ownerGroupId: string;
      pieceId: string;
      input: DrawingTraceRef;
    }
  | { kind: "slot"; slot: number; input: DrawingTraceRef };

/** One request-local interner of equal drawing nodes. */
export class DrawingNodePool {
  private readonly interned = new Map<string, DrawingNode>();
  private nextId = 0;

  /**
   * Return one interned drawing node for a native identity and its child slots.
   *
   * Children are stored in ascending slot order. Equal content within one calculation shares one
   * node, so a shared occurrence keeps one node identity.
   */
  node(
    ownerGroupId: string,
    pieceId: string,
    children: readonly DrawingChild[],
  ): DrawingNode {
    const ordered = [...children].sort(
      (first, second) => first.slot - second.slot,
    );
    const key = JSON.stringify([
      ownerGroupId,
      pieceId,
      ordered.map((child) => [child.slot, child.node.id]),
    ]);
    const existing = this.interned.get(key);
    if (existing !== undefined) {
      return existing;
    }
    const node: DrawingNode = {
      id: this.nextId,
      ownerGroupId,
      pieceId,
      children: ordered,
    };
    this.nextId += 1;
    this.interned.set(key, node);
    return node;
  }
}

const ZERO = 0;
const ONE = 1;

/** Split one read-only family handle into its low and high branches at one variable. */
function split<V>(
  nodes: readonly (readonly [V, number, number])[],
  order: VariableOrder<V>,
  handle: number,
  variable: V,
): [number, number] {
  if (handle < 2) {
    return [handle, ZERO];
  }
  const node = nodes[handle - 2];
  if (node === undefined) {
    throw new Error(`family handle ${handle} has no node`);
  }
  const compared = order.compare(node[0], variable);
  if (compared < 0) {
    throw new Error(`family handle ${handle} precedes the selected variable`);
  }
  if (compared > 0) {
    return [handle, ZERO];
  }
  return [node[1], node[2]];
}

/**
 * Return the first correlated operand pair whose union is the target member, or `null`.
 *
 * All operands are read-only views of one family. Both operands may carry the same variable, so
 * the pair is found by a correlated walk and never by subtracting one operand from the target.
 * Branches are tried low/high, then high/low, then high/high.
 */
export function firstJoinPair<V>(
  nodes: readonly (readonly [V, number, number])[],
  order: VariableOrder<V>,
  first: number,
  second: number,
  member: readonly V[],
): [V[], V[]] | null {
  const memo = new Map<string, [V[], V[]] | null>();

  const visit = (
    left: number,
    right: number,
    position: number,
  ): [V[], V[]] | null => {
    if (left === ZERO || right === ZERO) {
      return null;
    }
    if (left === ONE && right === ONE) {
      return position === member.length ? [[], []] : null;
    }
    const key = `${left}|${right}|${position}`;
    const cached = memo.get(key);
    if (cached !== undefined) {
      return cached;
    }
    const leftTop = left >= 2 ? nodes[left - 2][0] : undefined;
    const rightTop = right >= 2 ? nodes[right - 2][0] : undefined;
    let variable: V;
    let targeted: boolean;
    if (position < member.length) {
      variable = member[position];
      if (leftTop !== undefined && order.compare(leftTop, variable) < 0) {
        variable = leftTop;
      }
      if (rightTop !== undefined && order.compare(rightTop, variable) < 0) {
        variable = rightTop;
      }
      targeted = order.compare(variable, member[position]) === 0;
    } else {
      if (leftTop === undefined && rightTop === undefined) {
        throw new Error("join preimage has no remaining variable");
      }
      variable =
        leftTop === undefined
          ? (rightTop as V)
          : rightTop === undefined
            ? leftTop
            : order.compare(leftTop, rightTop) <= 0
              ? leftTop
              : rightTop;
      targeted = false;
    }
    const [leftLow, leftHigh] = split(nodes, order, left, variable);
    const [rightLow, rightHigh] = split(nodes, order, right, variable);
    let result: [V[], V[]] | null;
    if (!targeted) {
      result = visit(leftLow, rightLow, position);
    } else {
      const lowHigh = visit(leftLow, rightHigh, position + 1);
      if (lowHigh !== null) {
        result = [lowHigh[0], [variable, ...lowHigh[1]]];
      } else {
        const highLow = visit(leftHigh, rightLow, position + 1);
        if (highLow !== null) {
          result = [[variable, ...highLow[0]], highLow[1]];
        } else {
          const highHigh = visit(leftHigh, rightHigh, position + 1);
          result =
            highHigh === null
              ? null
              : [
                  [variable, ...highHigh[0]],
                  [variable, ...highHigh[1]],
                ];
        }
      }
    }
    memo.set(key, result);
    return result;
  };

  return visit(first, second, 0);
}

/**
 * Return the first source member whose predicate projection is the target member, or `null`.
 *
 * A projected-away source variable may be absent or present without consuming the target, and its
 * presence is restored into the returned member. A retained variable is present exactly when it is
 * the next target variable. The walk reads only handles.
 */
export function firstProjectPreimage<V>(
  nodes: readonly (readonly [V, number, number])[],
  order: VariableOrder<V>,
  source: number,
  member: readonly V[],
  predicate: (variable: V) => boolean,
): V[] | null {
  const memo = new Map<string, V[] | null>();

  const visit = (handle: number, position: number): V[] | null => {
    if (handle === ZERO) {
      return null;
    }
    if (handle === ONE) {
      return position === member.length ? [] : null;
    }
    const key = `${handle}|${position}`;
    const cached = memo.get(key);
    if (cached !== undefined) {
      return cached;
    }
    const node = nodes[handle - 2];
    if (node === undefined) {
      throw new Error(`family handle ${handle} has no node`);
    }
    const [variable, low, high] = node;
    let result: V[] | null;
    if (predicate(variable)) {
      const absent = visit(low, position);
      if (absent !== null) {
        result = absent;
      } else {
        const present = visit(high, position);
        result = present === null ? null : [variable, ...present];
      }
    } else if (position === member.length) {
      result = visit(low, position);
    } else {
      const compared = order.compare(variable, member[position]);
      if (compared < 0) {
        result = visit(low, position);
      } else if (compared === 0) {
        const matched = visit(high, position + 1);
        result = matched === null ? null : [variable, ...matched];
      } else {
        result = null;
      }
    }
    memo.set(key, result);
    return result;
  };

  return visit(source, 0);
}
