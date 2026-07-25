import { useState } from 'react'

/**
 * Hand-rolled SVG node-link view of the story-canon knowledge graph.
 *
 * Zero-dependency (follows the `ScoreGauge` inline-`<svg>` precedent). Expects a
 * laid-out view-model from `toCanonGraphView` — nodes carry absolute x/y and a
 * type `label`; edges carry endpoint coordinates. Colours stay on-palette:
 * black for characters, soft red for the episode, outlined surfaces otherwise.
 */

const NODE_R = 9

const NODE_STYLE = {
  Episode: { fill: 'var(--accent)', stroke: 'var(--accent)', text: 'var(--white)' },
  Character: { fill: 'var(--ink)', stroke: 'var(--ink)', text: 'var(--white)' },
  AudienceSegment: { fill: 'var(--surface)', stroke: 'var(--accent)', text: 'var(--ink)' },
  Fact: { fill: 'var(--surface)', stroke: 'var(--dim)', text: 'var(--muted)' },
  _default: { fill: 'var(--surface-raised)', stroke: 'var(--ink)', text: 'var(--ink)' },
}

function styleFor(label) {
  return NODE_STYLE[label] || NODE_STYLE._default
}

export default function GraphCanvas({ data }) {
  const [hovered, setHovered] = useState(null)
  if (!data || data.isEmpty) return null

  const { width, height, nodes, edges } = data

  return (
    <div style={{ width: '100%', overflowX: 'auto' }}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        style={{ display: 'block', maxWidth: width, margin: '0 auto' }}
        role="img"
        aria-label="Story canon knowledge graph"
      >
        {edges.map((e) => (
          <line
            key={e.id}
            x1={e.x1}
            y1={e.y1}
            x2={e.x2}
            y2={e.y2}
            stroke="var(--border)"
            strokeWidth={1}
          />
        ))}

        {nodes.map((node) => {
          const s = styleFor(node.label)
          const active = hovered === node.id
          const label = node.name.length > 22 ? `${node.name.slice(0, 20)}…` : node.name
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
                r={active ? NODE_R + 3 : NODE_R}
                fill={s.fill}
                stroke={s.stroke}
                strokeWidth={active ? 2.5 : 1.5}
                style={{ transition: 'r var(--dur-fast) var(--ease-standard)' }}
              />
              <text
                x={node.x}
                y={node.y + NODE_R + 13}
                textAnchor="middle"
                style={{
                  fontFamily: 'var(--font-sans)',
                  fontSize: 11,
                  fontWeight: 600,
                  fill: 'var(--ink)',
                  pointerEvents: 'none',
                }}
              >
                {label}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
