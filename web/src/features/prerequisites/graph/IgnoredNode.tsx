/** Muted annotation node for a compiler-disclosed ignored source part. */
import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { GraphNodeData } from "./CourseNode";

export function IgnoredNode({ data }: NodeProps & { data: GraphNodeData }) {
  return (
    <div className="graph-ignored" title={data.subtitle}>
      <Handle type="target" position={Position.Top} />
      {data.title}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
