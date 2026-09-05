import { BaseEdge, EdgeLabelRenderer, type EdgeProps } from "@xyflow/react";
import type { CSSProperties } from "react";
import type { WorkspaceEdge } from "@/lib/graph";
import { useDesignNodeActions } from "./design-node-actions";

export function RoleEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
  selected,
}: EdgeProps<WorkspaceEdge>) {
  const actions = useDesignNodeActions();
  const subject = data?.role === "subject";
  const broken = data?.state === "deleted";
  const active = data?.highlighted || selected;
  const color = broken
    ? "var(--wire-error)"
    : subject
      ? "var(--wire-subject)"
      : "var(--wire-reference)";
  const sx = broken ? targetX - 72 : sourceX;
  const sy = broken ? targetY : sourceY;
  // Both tracks use the same monotone horizontal controls, so their vertical
  // ordering is preserved even when cards have different heights or are close.
  const offset = Math.max(12, Math.abs(targetX - sx) * 0.45);
  const path = `M ${sx},${sy} C ${sx + offset},${sy} ${targetX - offset},${targetY} ${targetX},${targetY}`;
  const x = (sx + targetX) / 2,
    y = (sy + targetY) / 2;
  const opacity = data?.dimmed ? 0.25 : data?.state === "empty" ? 0.4 : 1;
  const label = subject ? "Disconnect input" : "Remove reference";
  return (
    <>
      <g style={{ opacity, color }}>
        <BaseEdge
          id={id}
          path={path}
          interactionWidth={0}
          style={{
            pointerEvents: "none",
            stroke: color,
            strokeWidth: active ? 3.5 : subject ? 2.5 : 1.5,
            strokeDasharray: broken || !subject ? "6 4" : undefined,
          }}
        />
        {/* Keep the large wire hit area away from the draggable handles. */}
        <path
          className="react-flow__edge-interaction"
          d={`M ${sx + 16},${sy} C ${sx + offset},${sy} ${targetX - offset},${targetY} ${targetX - 16},${targetY}`}
          fill="none"
          stroke="transparent"
          strokeWidth={24}
          style={{ pointerEvents: "stroke" }}
        />
        <path
          d={`M ${targetX - 13} ${targetY - 5} L ${targetX - 6} ${targetY} L ${targetX - 13} ${targetY + 5}${subject ? " Z" : ""}`}
          fill={subject ? color : "none"}
          stroke={color}
          strokeWidth="1.5"
          style={{ pointerEvents: "none" }}
        />
        {[
          { x: sx, y: sy },
          { x: targetX, y: targetY },
        ].map((point, i) => (
          <g
            key={i}
            transform={`translate(${point.x},${point.y})`}
            className="pointer-events-none"
          >
            {active ? (
              <circle r="8" fill="none" stroke={color} strokeWidth="1.5" />
            ) : null}
            <circle
              className="wire-endpoint"
              fill={subject ? color : "white"}
              stroke={color}
              strokeWidth="1.5"
            />
          </g>
        ))}
      </g>
      <EdgeLabelRenderer>
        <button
          type="button"
          aria-label={label}
          title={label}
          data-wire-id={id}
          data-number={data?.number}
          onMouseMove={() => actions.hoverWire(id)}
          onMouseEnter={() => actions.hoverWire(id)}
          onMouseLeave={() => actions.hoverWire(null)}
          onFocus={() => actions.hoverWire(id)}
          onBlur={() => actions.hoverWire(null)}
          onClick={() => actions.deleteWire(id)}
          className={`wire-badge nodrag nopan ${subject && !broken ? "filled" : ""} ${active ? "active" : ""}`}
          style={
            {
              transform: `translate(-50%, -50%) translate(${x}px, ${y}px)`,
              opacity,
              "--badge-color": color,
            } as CSSProperties
          }
        >
          <span className="badge-number">
            {broken ? "!" : data?.state === "empty" ? "" : data?.number}
          </span>
          <span className="badge-remove" aria-hidden="true">
            ×
          </span>
        </button>
      </EdgeLabelRenderer>
    </>
  );
}
