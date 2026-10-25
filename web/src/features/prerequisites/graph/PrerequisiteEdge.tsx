/** Orthogonal ELK edge with parent hue and a dashed style for an all-inferred connection. */
import { BaseEdge, type EdgeProps } from "@xyflow/react";

const HUES = ["#5a77b3", "#4f9c7c", "#a3834f", "#8670ad", "#a86f82", "#4f8f9b"];
/** Render one orthogonal graph edge in its parent hue or inferred dash style. */
export function PrerequisiteEdge({ id, data }: EdgeProps) {
  const edge = data as
    | {
        points?: readonly { x: number; y: number }[];
        parentIndex?: number;
        inferred?: boolean;
        delay?: string;
        opacity?: number;
      }
    | undefined;
  const points = edge?.points ?? [];
  const path = points.reduce((d, point, index) => {
    if (!index) return `M${point.x},${point.y}`;
    if (index === points.length - 1 || points.length < 3)
      return `${d} L${point.x},${point.y}`;
    const before = points[index - 1],
      after = points[index + 1];
    const inX = point.x - before.x,
      inY = point.y - before.y,
      outX = after.x - point.x,
      outY = after.y - point.y;
    const inLength = Math.hypot(inX, inY),
      outLength = Math.hypot(outX, outY);
    const cross = inX * outY - inY * outX;
    if (!inLength || !outLength || !cross) return `${d} L${point.x},${point.y}`;
    const radius = Math.min(10, inLength / 2, outLength / 2);
    const inUnitX = inX / inLength,
      inUnitY = inY / inLength,
      outUnitX = outX / outLength,
      outUnitY = outY / outLength;
    return `${d} L${point.x - inUnitX * radius},${point.y - inUnitY * radius} Q${point.x},${point.y} ${point.x + outUnitX * radius},${point.y + outUnitY * radius}`;
  }, "");
  const color = HUES[(edge?.parentIndex ?? 0) % HUES.length];
  const className = `prereq-edge${edge?.inferred ? " inferred" : ""}`;
  // React Flow hands the edge style to this component, not to its wrapper group, so the frame's
  // fade opacity and the route's per-edge light-up delay both have to live on this group.
  return (
    <g
      style={
        {
          opacity: edge?.opacity ?? 1,
          "--dl": edge?.delay,
        } as React.CSSProperties
      }
    >
      <BaseEdge
        id={`${id}-halo`}
        path={path}
        className={`${className} halo`}
        style={
          {
            stroke: "#0a0a0f",
            strokeWidth: 6,
          } as React.CSSProperties
        }
      />
      <BaseEdge
        id={id}
        path={path}
        className={`${className} line`}
        style={
          {
            stroke: color,
            "--edge-color": color,
          } as React.CSSProperties
        }
      />
    </g>
  );
}
