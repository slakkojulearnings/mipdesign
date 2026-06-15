import React, { useMemo } from "react";

// Draws field flows as a simple left-to-right SVG: distinct sources on the left,
// targets on the right, an arrow per flow labelled with its kind. Hovering a flow
// shows kind + evidence (SVG <title>). Reuses the app's color language.
//
// flows: [{ src, dst, kind, evidence }]
export default function LineageDiagram({ flows }) {
  const lay = useMemo(() => {
    const sources = [], targets = [], si = {}, ti = {};
    for (const f of flows) {
      if (!(f.src in si)) { si[f.src] = sources.length; sources.push(f.src); }
      if (!(f.dst in ti)) { ti[f.dst] = targets.length; targets.push(f.dst); }
    }
    const rowH = 34, padY = 16, padX = 12, nodeW = 180, gap = 150;
    const rows = Math.max(sources.length, targets.length, 1);
    const height = padY * 2 + rows * rowH;
    const leftX = padX, rightX = padX + nodeW + gap;
    const width = rightX + nodeW + padX;
    const yOf = (i) => padY + i * rowH + rowH / 2;
    return { sources, targets, si, ti, rowH, padX, nodeW, leftX, rightX, width, height, yOf };
  }, [flows]);

  const { sources, targets, si, ti, rowH, nodeW, leftX, rightX, width, height, yOf } = lay;

  return (
    <div className="lineage-wrap">
      <svg width={width} height={Math.max(height, 60)} className="lineage-svg">
        <defs>
          <marker id="lin-arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
            <path d="M0,0 L7,3 L0,6 Z" fill="var(--purple)" />
          </marker>
        </defs>

        {flows.map((f, i) => {
          const y1 = yOf(si[f.src]), y2 = yOf(ti[f.dst]);
          const x1 = leftX + nodeW, x2 = rightX;
          const mx = (x1 + x2) / 2;
          return (
            <g key={i}>
              <path d={`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`}
                    fill="none" stroke="var(--purple)" strokeWidth="1.6"
                    markerEnd="url(#lin-arrow)" opacity="0.85">
                <title>{`${f.src} → ${f.dst}  ·  ${f.kind}  ·  ${f.evidence}`}</title>
              </path>
            </g>
          );
        })}

        {sources.map((s, i) => (
          <g key={"s" + s} transform={`translate(${leftX},${yOf(i) - rowH / 2 + 4})`}>
            <rect width={nodeW} height={rowH - 8} rx="7" fill="var(--panel-2)" stroke="var(--border-strong)" />
            <text x="10" y={(rowH - 8) / 2 + 4} fontSize="11.5"
                  fontFamily="ui-monospace, Consolas, monospace" fill="var(--text)">{s}</text>
          </g>
        ))}

        {targets.map((t, i) => (
          <g key={"t" + t} transform={`translate(${rightX},${yOf(i) - rowH / 2 + 4})`}>
            <rect width={nodeW} height={rowH - 8} rx="7" fill="var(--panel-2)" stroke="rgba(94,92,230,.45)" />
            <text x="10" y={(rowH - 8) / 2 + 4} fontSize="11.5"
                  fontFamily="ui-monospace, Consolas, monospace" fill="var(--text)">{t}</text>
          </g>
        ))}
      </svg>
    </div>
  );
}
