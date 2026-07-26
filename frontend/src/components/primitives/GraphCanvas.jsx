import { useState } from 'react'

/**
 * Hand-rolled SVG view of the story-canon knowledge graph.
 *
 * Zero-dependency (follows the `ScoreGauge` inline-`<svg>` precedent). Consumes
 * the clustered layout from `toCanonGraphView`: nodes carry absolute x/y/r and a
 * type `label`; clusters carry a disc centre + an outward type label; edges
 * carry endpoint coordinates plus their source/target ids for the hover focus.
 *
 * Node dots are unlabelled so the view stays legible past 100 nodes — the type
 * sits on the cluster, and a name appears on hover. Colours stay on-palette:
 * soft red for episodes, black for characters, a calm grey ramp for the rest.
 */

/** Per-type node colours. Shared with `GraphLegend` so the two never drift. */
const NODE_TYPE_STYLE = {
  Episode: { fill: 'var(--accent)', stroke: 'var(--accent)' },
  Character: { fill: 'var(--ink)', stroke: 'var(--ink)' },
  Location: { fill: 'var(--muted)', stroke: 'var(--muted)' },
  PlotThread: { fill: 'var(--grey-600, #8a8a8a)', stroke: 'var(--grey-600, #8a8a8a)' },
  Clue: { fill: 'var(--dim)', stroke: 'var(--muted)' },
  Theme: { fill: 'var(--surface-raised)', stroke: 'var(--ink)' },
  AudienceSegment: { fill: 'var(--surface-raised)', stroke: 'var(--accent)' },
  Fact: { fill: 'var(--surface)', stroke: 'var(--dim)' },
  _default: { fill: 'var(--surface-raised)', stroke: 'var(--ink)' },
}

function styleFor(label) {
  return NODE_TYPE_STYLE[label] || NODE_TYPE_STYLE._default
}

/** Node-type legend whose swatches match the graph colours exactly. */
export function GraphLegend({ stats }) {
  const types = Object.keys(stats || {}).filter((k) => k !== 'edges')
  if (!types.length) return null
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14 }}>
      {types.map((t) => {
        const s = styleFor(t)
        return (
          <span
            key={t}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 12, color: 'var(--muted)' }}
          >
            <span
              style={{
                width: 10,
                height: 10,
                borderRadius: '50%',
                background: s.fill,
                border: `1.5px solid ${s.stroke}`,
                flexShrink: 0,
              }}
            />
            {t} · {stats[t]}
          </span>
        )
      })}
    </div>
  )
}

/** Tallest the graph renders on wide screens (SVG units → px cap). */
const TARGET_MAX_H = 640

/** The hovered node's name, on a dark chip, drawn above (or below, if clipped). */
function HoverLabel({ node, minY }) {
  const text = node.name.length > 32 ? `${node.name.slice(0, 30)}…` : node.name
  const w = text.length * 6.6 + 16
  const h = 20
  const above = node.y - node.r - 8 - h
  const below = above < minY + 2
  const y = below ? node.y + node.r + 8 : above
  return (
    <g pointerEvents="none">
      <rect x={node.x - w / 2} y={y} width={w} height={h} rx={6} fill="var(--ink)" opacity={0.92} />
      <text
        x={node.x}
        y={y + h / 2 + 0.5}
        textAnchor="middle"
        dominantBaseline="middle"
        style={{ fontFamily: 'var(--font-sans)', fontSize: 11.5, fontWeight: 600, fill: 'var(--white)' }}
      >
        {text}
      </text>
    </g>
  )
}

export default function GraphCanvas({ data }) {
  const [hovered, setHovered] = useState(null)
  if (!data || data.isEmpty) return null

  const { viewBox, width, height, nodes, edges, clusters = [] } = data

  // Neighbours of the hovered node, so we can focus its slice of the graph.
  let neighbours = null
  if (hovered) {
    neighbours = new Set([hovered])
    for (const e of edges) {
      if (e.source === hovered) neighbours.add(e.target)
      else if (e.target === hovered) neighbours.add(e.source)
    }
  }

  const aspect = height > 0 ? width / height : 1
  const maxW = Math.round(TARGET_MAX_H * aspect)
  const minY = viewBox ? Number(viewBox.split(' ')[1]) : 0
  const hoveredNode = hovered ? nodes.find((n) => n.id === hovered) : null

  return (
    <div style={{ width: '100%', display: 'flex', justifyContent: 'center' }}>
      <svg
        viewBox={viewBox || `0 0 ${width} ${height}`}
        width="100%"
        style={{ display: 'block', width: '100%', height: 'auto', maxWidth: maxW }}
        role="img"
        aria-label="Story canon knowledge graph"
      >
        {/* Soft grouping halo behind each cluster. */}
        {clusters.map((c) => (
          <circle key={`halo-${c.type}`} cx={c.cx} cy={c.cy} r={c.discR + 12} fill="var(--surface)" opacity={0.75} />
        ))}

        {/* Edges — faint by default; the hovered node's edges light up red. */}
        {edges.map((e) => {
          const incident = hovered && (e.source === hovered || e.target === hovered)
          return (
            <line
              key={e.id}
              x1={e.x1}
              y1={e.y1}
              x2={e.x2}
              y2={e.y2}
              stroke={incident ? 'var(--accent)' : 'var(--dim)'}
              strokeWidth={incident ? 1.6 : 1}
              opacity={hovered ? (incident ? 0.9 : 0.12) : 0.35}
            />
          )
        })}

        {/* Cluster type labels. */}
        {clusters.map((c) => (
          <text
            key={`lbl-${c.type}`}
            x={c.labelX}
            y={c.labelY}
            textAnchor="middle"
            dominantBaseline="middle"
            style={{ fontFamily: 'var(--font-sans)', fontSize: 12.5, fontWeight: 600, fill: 'var(--ink)', pointerEvents: 'none' }}
          >
            {c.label} · {c.count}
          </text>
        ))}

        {/* Nodes. */}
        {nodes.map((node) => {
          const s = styleFor(node.label)
          const active = hovered === node.id
          const dim = hovered && neighbours && !neighbours.has(node.id)
          return (
            <g
              key={node.id}
              onMouseEnter={() => setHovered(node.id)}
              onMouseLeave={() => setHovered(null)}
            >
              <title>
                {node.label}: {node.name}
                {node.description ? ` — ${node.description}` : ''}
              </title>
              <circle
                cx={node.x}
                cy={node.y}
                r={active ? node.r + 2.5 : node.r}
                fill={s.fill}
                stroke={s.stroke}
                strokeWidth={active ? 2.5 : 1.5}
                opacity={dim ? 0.3 : 1}
                style={{ transition: 'r var(--dur-fast) var(--ease-standard)' }}
              />
            </g>
          )
        })}

        {/* Hovered name, drawn last so it sits above everything. */}
        {hoveredNode && <HoverLabel node={hoveredNode} minY={minY} />}
      </svg>
    </div>
  )
}
