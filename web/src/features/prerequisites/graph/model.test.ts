/** Directional highlight boundaries of one hovered or opened graph node. */
import { describe, expect, it } from "vitest";
import { connectionChain, type GraphModel, type ModelNode } from "./model";

const node = (id: string, kind: ModelNode["kind"]): ModelNode => ({
  id,
  kind,
  size: { width: 100, height: 40 },
  markKey: null,
  markable: false,
  state: null,
  title: id,
  subtitle: "",
});
const edge = (source: string, target: string) => ({
  id: `${source}->${target}`,
  source,
  target,
  inferred: false,
  parentIndex: 0,
  memberIds: [],
});
const model: GraphModel = {
  nodes: [
    node("grandparent", "course"),
    node("root", "course"),
    node("parent-and", "connector"),
    node("a", "course"),
    node("b", "course"),
    node("second-parent", "course"),
    node("module", "module"),
    node("child-or", "connector"),
    node("c", "course"),
    node("d", "course"),
    node("grandchild", "course"),
  ],
  edges: [
    edge("grandparent", "root"),
    edge("root", "parent-and"),
    edge("parent-and", "a"),
    edge("parent-and", "b"),
    edge("second-parent", "a"),
    edge("a", "module"),
    edge("module", "child-or"),
    edge("child-or", "c"),
    edge("child-or", "d"),
    edge("c", "grandchild"),
  ],
  rootId: "root",
};
const sorted = (values: Iterable<string>): string[] => [...values].sort();

describe("connection chain", () => {
  it("a course highlights only its nearest course parents and children", () => {
    const chain = connectionChain(model, "a");
    expect(sorted(chain.nodes)).toEqual([
      "a",
      "c",
      "child-or",
      "d",
      "module",
      "parent-and",
      "root",
      "second-parent",
    ]);
    expect(sorted(chain.edges)).toEqual([
      "a->module",
      "child-or->c",
      "child-or->d",
      "module->child-or",
      "parent-and->a",
      "root->parent-and",
      "second-parent->a",
    ]);
  });

  it("a box highlights directional course boundaries without sibling detours", () => {
    const chain = connectionChain(model, "module");
    expect(sorted(chain.nodes)).toEqual(["a", "c", "child-or", "d", "module"]);
    expect(sorted(chain.edges)).toEqual([
      "a->module",
      "child-or->c",
      "child-or->d",
      "module->child-or",
    ]);
  });
});
