---
name: pocketfm-ui-design
description: Create, redesign, review, or polish PocketFM web interfaces with the shared Lexend, white, black, and soft-red visual system. Use for any task touching frontend pages, React components, dashboards, forms, navigation, landing pages, responsive layouts, CSS, visual hierarchy, accessibility, or UI/UX copy. Do not use for backend-only, infrastructure-only, or non-visual data tasks.
---

# PocketFM UI Design

Apply one consistent interface system across every frontend surface, regardless of
framework or coding agent.

## Required workflow

1. Inspect the existing UI, framework, tokens, assets, and responsive behavior.
2. Read [references/design-system.md](references/design-system.md) completely
   before making visual decisions.
3. Preserve working behavior and established product flows. Change information
   architecture only when the task requires it.
4. Reuse or adapt [assets/ui-tokens.css](assets/ui-tokens.css) when the project
   lacks equivalent shared tokens. Do not create competing token systems.
5. Build the smallest coherent set of reusable components and styles needed for
   the requested surface.
6. Check desktop and mobile layouts, keyboard interaction, focus states, loading,
   empty, error, success, and disabled states that apply to the flow.
7. Run the repository's formatter, lint, tests, and production build.
8. Visually inspect the result at representative desktop and mobile widths when
   browser or screenshot tooling is available.

## Non-negotiable visual direction

- Use **Lexend** for headings, body copy, labels, inputs, and buttons.
- Use a white canvas with black primary text and black primary CTA buttons.
- Use soft red with white as a supporting combination for highlights, selected
  states, status surfaces, charts, and gentle emphasis.
- Keep the primary hierarchy black. Never let red compete with the main CTA.
- Prefer whitespace, typography, thin borders, and restrained surfaces over
  decorative containers.
- Keep layouts clean, calm, responsive, and immediately understandable.
- Use concise, human interface copy. Remove starter-template and placeholder copy.

## Implementation rules

- Define shared color, spacing, typography, radius, shadow, and motion tokens.
- Prefer semantic components and class names over repeated inline styles.
- Keep touch targets at least 44px and visible focus indicators on controls.
- Use icons only when they improve recognition; use one consistent icon family.
- Use motion sparingly, honor `prefers-reduced-motion`, and avoid blocking effects.
- Do not introduce gradients, glassmorphism, neon colors, excessive shadows,
  oversized rounding, decorative pills, or card grids without a content reason.
- Do not use red for long body text or rely on color alone to communicate state.
- Do not ship a dark theme unless the user explicitly asks for one.

## Completion contract

Report:

- the surfaces or components changed;
- how the shared tokens and hierarchy were applied;
- desktop/mobile and accessibility checks performed;
- lint, test, and build results;
- any deliberate exception to this skill, with its product reason.
