/**
 * Ready-made cover images for the Audience Simulator composer — mirrors the
 * "Load a ready-made story" picker so a presenter can attach an image in one
 * click, no upload needed. Each cover is drawn client-side on a <canvas> and
 * exported as a real JPEG (base64), so the vision model genuinely "sees" it —
 * no binary assets are shipped in the bundle.
 */

export const IMAGE_LIBRARY = [
  { id: 'thriller', label: 'Supernatural Thriller', genre: 'SUPERNATURAL THRILLER', bg: ['#141428', '#7b2d3b'], accent: '#f4b8b8' },
  { id: 'romance', label: 'Romance Drama', genre: 'ROMANCE', bg: ['#5a1f2b', '#e08aa0'], accent: '#ffe6ec' },
  { id: 'crime', label: 'Crime / Detective', genre: 'CRIME · DETECTIVE', bg: ['#0e0e12', '#3a3a44'], accent: '#e96b6b' },
  { id: 'mythology', label: 'Mythology / Historical', genre: 'MYTHOLOGY', bg: ['#3a230b', '#c8860a'], accent: '#ffe0a3' },
  { id: 'scifi', label: 'Science Fiction', genre: 'SCIENCE FICTION', bg: ['#08131f', '#1f8a9a'], accent: '#a8ecf5' },
  { id: 'mystery', label: 'Mystery / Thriller', genre: 'MYSTERY', bg: ['#101820', '#4b6a7a'], accent: '#cfe6f0' },
]

export const IMAGE_BY_ID = Object.fromEntries(IMAGE_LIBRARY.map((i) => [i.id, i]))

function wrapText(ctx, text, x, y, maxWidth, lineHeight, maxLines) {
  const words = String(text || '').split(/\s+/).filter(Boolean)
  let line = ''
  let lines = 0
  for (const w of words) {
    const test = line ? `${line} ${w}` : w
    if (ctx.measureText(test).width > maxWidth && line) {
      ctx.fillText(line, x, y)
      line = w
      y += lineHeight
      lines += 1
      if (lines >= maxLines - 1) break
    } else {
      line = test
    }
  }
  ctx.fillText(line, x, y)
}

/**
 * Render a themed cover to a JPEG data URL. `title` ties the cover to the post.
 * @returns {{dataUrl:string, base64:string, mime:string, name:string}}
 */
export function renderCover(sample, title) {
  const W = 1024
  const H = 576
  const canvas = document.createElement('canvas')
  canvas.width = W
  canvas.height = H
  const ctx = canvas.getContext('2d')

  const g = ctx.createLinearGradient(0, 0, W, H)
  g.addColorStop(0, sample.bg[0])
  g.addColorStop(1, sample.bg[1])
  ctx.fillStyle = g
  ctx.fillRect(0, 0, W, H)

  // Subtle vignette for depth.
  const rg = ctx.createRadialGradient(W / 2, H / 2, H / 4, W / 2, H / 2, H)
  rg.addColorStop(0, 'rgba(0,0,0,0)')
  rg.addColorStop(1, 'rgba(0,0,0,0.35)')
  ctx.fillStyle = rg
  ctx.fillRect(0, 0, W, H)

  // Genre eyebrow.
  ctx.fillStyle = sample.accent
  ctx.font = '700 26px Lexend, system-ui, sans-serif'
  ctx.fillText(sample.genre, 64, 96)

  // Title (wrapped, tied to the post).
  ctx.fillStyle = '#ffffff'
  ctx.font = '800 72px Lexend, system-ui, sans-serif'
  wrapText(ctx, title || sample.label, 64, 300, W - 128, 84, 3)

  // Footer tag.
  ctx.fillStyle = 'rgba(255,255,255,0.7)'
  ctx.font = '600 22px Lexend, system-ui, sans-serif'
  ctx.fillText('PocketFM · new episode', 64, H - 56)

  const dataUrl = canvas.toDataURL('image/jpeg', 0.85)
  return {
    dataUrl,
    base64: dataUrl.split(',')[1] || '',
    mime: 'image/jpeg',
    name: `${sample.id}-cover.jpg`,
  }
}
