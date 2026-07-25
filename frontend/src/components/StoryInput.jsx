import { SCENE_DELIMITER } from '../config/constants'
import { countScenes, countWords } from '../utils/story'
import { Button } from './primitives'

/**
 * Episode-text editor + run control.
 *
 * Fully controlled: `value`/`onChange` own the text, `onRun` fires the active
 * lens. Scene/word counts come from the story utils — no logic lives here.
 */
export default function StoryInput({ value, onChange, onRun, loading, canRun }) {
  const scenes = countScenes(value)
  const words = countWords(value)

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <label htmlFor="studio-story" className="label-upper" style={{ fontSize: 11 }}>
        Episode text
      </label>
      <textarea
        id="studio-story"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
        style={{
          width: '100%',
          minHeight: 140,
          boxSizing: 'border-box',
          resize: 'vertical',
          fontFamily: 'var(--font-mono)',
          fontSize: 14,
          lineHeight: 1.6,
          color: 'var(--ink)',
          background: 'var(--canvas)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          padding: 16,
        }}
      />
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 12,
        }}
      >
        <span style={{ fontSize: 13, color: 'var(--muted)', whiteSpace: 'nowrap' }}>
          {scenes} {scenes === 1 ? 'scene' : 'scenes'} · {words} words · split on{' '}
          <code style={{ fontFamily: 'var(--font-mono)' }}>{SCENE_DELIMITER}</code>
        </span>
        <Button variant="primary" onClick={onRun} disabled={!canRun}>
          {loading ? 'Simulating…' : 'Run simulation'}
        </Button>
      </div>
    </section>
  )
}
