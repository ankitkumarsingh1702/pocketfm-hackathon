/** Barrel export for the presentational primitive components. */
export { default as AgentLogConsole } from './AgentLogConsole'
export { default as BarChart } from './BarChart'
export { default as Button } from './Button'
export { default as Disclosure } from './Disclosure'
export { default as GraphCanvas, GraphLegend } from './GraphCanvas'
export { default as Icon } from './Icon'
// MermaidDiagram is deliberately NOT exported here. This barrel is imported by
// almost every component, so anything in it joins the entry chunk's module
// graph — and that component's whole purpose is to pull in a multi-megabyte
// renderer. Import it directly from './MermaidDiagram' at the one call site that
// needs it, behind a lazy boundary.
export { default as MetricNumber } from './MetricNumber'
export { default as Pill } from './Pill'
export { default as ProgressLine } from './ProgressLine'
export { default as QuoteCard } from './QuoteCard'
export { default as ScoreGauge } from './ScoreGauge'
export { default as SideSheet } from './SideSheet'
export { default as SurfaceCard } from './SurfaceCard'
export { default as Tabs } from './Tabs'
export { default as Wordmark } from './Wordmark'
