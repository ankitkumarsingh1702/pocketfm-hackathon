# PocketFM interface system

## 1. Design character

The interface should feel editorial, focused, modern, and trustworthy. Use a
white-first composition, confident black typography, black primary actions, and
soft red accents. Let spacing and type create hierarchy.

Aim for:

- immediate comprehension;
- strong reading rhythm;
- high contrast where action matters;
- gentle red warmth without visual noise;
- production polish on desktop and mobile.

Avoid generic AI-dashboard styling, crowded card walls, and decorative effects
that do not improve comprehension.

## 2. Color tokens

Use these values as the default palette. Map them to the host framework's token
format instead of duplicating them.

| Role | Token | Value | Use |
| --- | --- | --- | --- |
| Canvas | `--ui-bg` | `#FFFFFF` | Page background |
| Primary ink | `--ui-ink` | `#111111` | Headings, primary text, primary CTA |
| Muted ink | `--ui-ink-muted` | `#626262` | Supporting copy |
| Subtle ink | `--ui-ink-subtle` | `#8A8A8A` | Metadata and placeholders |
| Soft surface | `--ui-surface` | `#F8F8F6` | Secondary sections and controls |
| Border | `--ui-line` | `#E8E8E5` | Dividers and input borders |
| Soft red | `--ui-red` | `#E96B6B` | Icons, chart marks, controlled emphasis |
| Pale red | `--ui-red-soft` | `#FDECEC` | Selected or highlighted surfaces |
| Red border | `--ui-red-line` | `#F4B8B8` | Pale-red surface borders |
| Accessible red ink | `--ui-red-ink` | `#A93636` | Short labels on pale-red surfaces |
| CTA hover | `--ui-black-hover` | `#292929` | Primary CTA hover |

Rules:

- Keep primary actions black with white text.
- Use red-filled controls only for destructive actions.
- Use pale red for selected, alert, insight, and emphasis surfaces.
- Use accessible red ink for text; do not place soft red text directly on white.
- Keep most surfaces white. Use soft grey or pale red only to create meaning.

## 3. Typography

Use Lexend everywhere:

```css
font-family: "Lexend", ui-sans-serif, system-ui, -apple-system, sans-serif;
```

Load weights 300, 400, 500, 600, and 700. Prefer:

- display: `clamp(2.25rem, 5vw, 4.75rem)`, weight 600, tight line-height;
- page title: `clamp(1.75rem, 3vw, 2.75rem)`, weight 600;
- section title: `1.25rem` to `1.75rem`, weight 600;
- body: `0.95rem` to `1.05rem`, weight 400, line-height 1.6;
- label: `0.78rem` to `0.875rem`, weight 500 or 600;
- button: `0.9rem` to `1rem`, weight 600.

Use sentence case. Keep line lengths around 55-72 characters for long copy. Do not
use all caps for headings or paragraphs.

## 4. Layout and spacing

- Use a centered content width between 1120px and 1240px.
- Use page gutters of 20px mobile, 32px tablet, and 48px desktop.
- Use an 8px spacing rhythm with 4px only for tight label/icon relationships.
- Separate major sections by 64-112px desktop and 48-72px mobile.
- Use whitespace before adding borders, surfaces, or shadows.
- Prefer one strong composition over repeated equal-weight cards.
- Let dense data areas use tables, lists, or charts instead of nested cards.

Responsive behavior:

- Design mobile structure intentionally; do not merely shrink desktop.
- Stack primary content before supporting content.
- Keep key actions visible and full-width when helpful on narrow screens.
- Prevent horizontal overflow at 320px.
- Test around 375px, 768px, 1024px, and 1440px.

## 5. Components

### Primary CTA

- Black background, white label, 44-48px minimum height.
- Use 10-12px radius rather than a full pill.
- Hover to `#292929`; pressed state may translate by 1px.
- Keep one dominant primary action per region.

### Secondary action

- White or soft-surface background, black label, thin neutral border.
- Use soft-red border/ink only when the action is meaningfully tied to a red
  insight or selected state.

### Inputs

- White background, black text, neutral border, 44px minimum height.
- Use persistent labels. Placeholders are examples, not labels.
- Focus with a clear black ring or strong border.
- Error state: pale-red surface or red border plus explanatory text and an icon.

### Cards and panels

- Use only when grouping is necessary.
- Default to white with a thin border; use subtle shadow only for elevation.
- Use 14-18px radius. Avoid making every block a floating card.
- Prefer pale red for a single highlighted insight, not every panel.

### Navigation

- Keep it minimal and predictable.
- Use black for current/high-priority items and muted ink for secondary items.
- Use a red dot, underline, or pale-red background as a restrained active marker.

### Feedback states

- Loading: preserve layout and communicate progress.
- Empty: explain what the area is for and provide a useful next action.
- Error: state what happened and how to recover.
- Success: confirm the completed outcome without a large celebratory treatment.
- Disabled: reduce emphasis but retain legibility.

## 6. Accessibility and interaction

- Meet WCAG AA contrast for text and essential controls.
- Do not encode status by color alone; add text, icon, or shape.
- Use semantic landmarks, headings, buttons, labels, and tables.
- Keep keyboard order aligned with visual order.
- Make focus visible on every interactive element.
- Provide meaningful alt text; mark decorative images as decorative.
- Keep animations short and optional with `prefers-reduced-motion`.
- Respect browser zoom and dynamic text resizing.

## 7. Content style

- Use plain, direct, human language.
- Lead with the outcome or action.
- Keep labels short and specific.
- Avoid buzzwords, fake metrics, and explanatory paragraphs inside controls.
- Replace framework starter content before calling a surface complete.

## 8. Final review

Before completion, verify:

- Lexend is actually loaded and applied;
- white/black hierarchy is dominant;
- soft red is restrained and purposeful;
- primary CTAs are black and unambiguous;
- mobile layout is designed, not compressed;
- all relevant states are present;
- keyboard focus and contrast are sound;
- placeholder/starter UI is removed;
- lint, tests, and production build pass.
