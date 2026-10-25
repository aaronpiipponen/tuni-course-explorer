/** Project one chosen drawing derivation onto the drawn route nodes and lit members. */
import type { SolverStructure } from "../api/types";
import { compareText } from "./order";
import type { DrawingNode } from "./route-derivation";

/**
 * Return the drawn node IDs and lit member IDs for one chosen drawing derivation.
 *
 * The walk pairs each projected context with the selected drawing node for it and follows only the
 * child slots that node selected. The node set is the root plus the source and target endpoints of
 * every lit member. Every referenced context, member and native identity is a producer guarantee,
 * so an unresolved reference raises an error instead of lighting a fallback.
 */
export function projectRoute(
  structure: SolverStructure,
  drawing: DrawingNode,
): { selectedNodes: string[]; litMembers: string[] } {
  const contexts = new Map(
    structure.projection_contexts.map((context) => [
      context.context_id,
      context,
    ]),
  );
  const members = new Map(
    structure.members.map((member) => [member.member_id, member]),
  );
  const rootContextId = structure.projection_root_context_id;
  if (rootContextId === null) {
    throw new Error("a chosen route has no projection root context");
  }
  const litMemberIds = new Set<string>();
  const visited = new Set<string>();

  const visit = (contextId: string, node: DrawingNode): void => {
    const key = `${contextId}\u0000${node.id}`;
    if (visited.has(key)) {
      return;
    }
    visited.add(key);
    const context = contexts.get(contextId);
    if (context === undefined) {
      throw new Error(`unknown prerequisite projection context ${contextId}`);
    }
    if (
      context.owner_group_id !== node.ownerGroupId ||
      context.piece_id !== node.pieceId
    ) {
      throw new Error(
        `projection context ${contextId} does not match its selected drawing node`,
      );
    }
    for (const memberId of context.member_ids) {
      if (!members.has(memberId)) {
        throw new Error(`unknown prerequisite relationship member ${memberId}`);
      }
      litMemberIds.add(memberId);
    }
    const slots = new Map(
      context.children.map((child) => [child.slot, child.context_id]),
    );
    for (const child of node.children) {
      const childContextId = slots.get(child.slot);
      if (childContextId === undefined) {
        throw new Error(
          `projection context ${contextId} has no child in slot ${child.slot}`,
        );
      }
      visit(childContextId, child.node);
    }
  };

  visit(rootContextId, drawing);
  const nodeIds = new Set<string>([`course:${structure.root_group_id}`]);
  const litMembers = [...litMemberIds];
  for (const memberId of litMembers) {
    const member = members.get(memberId);
    if (member === undefined) {
      throw new Error(`unknown prerequisite relationship member ${memberId}`);
    }
    nodeIds.add(member.source_node_id);
    nodeIds.add(member.target_node_id);
  }
  return {
    selectedNodes: [...nodeIds].sort(compareText),
    litMembers: litMembers.sort(compareText),
  };
}
