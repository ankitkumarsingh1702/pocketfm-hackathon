import { Button } from '../primitives'

/**
 * The one clarifying question.
 *
 * Shown only when the query is too thin to split three ways honestly — "bore ho
 * raha hoon" carries no emotional content, so three distinct readings cannot be
 * generated from it without inventing them. Asking beats guessing here; asking
 * twice does not, so a skip drops the sparsity to zero and the next response is
 * shelves whatever happens.
 *
 * Every option resolves straight into mood space server-side, which is why
 * answering costs no second model call — the same mechanism the sliders use,
 * wearing different clothes.
 */
export default function MoodClarify({ question, onAnswer, busy = false }) {
  if (!question) return null

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 20, maxWidth: '56ch' }}>
      <div>
        <div className="label-upper" style={{ fontSize: 11, marginBottom: 10 }}>
          One question, then results
        </div>
        <h3
          style={{
            margin: 0,
            fontSize: 22,
            fontWeight: 600,
            lineHeight: 1.35,
            color: 'var(--ink)',
          }}
        >
          {question.question}
        </h3>
      </div>

      <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 10 }}>
        {question.options.map((option) => (
          <li key={option.id} style={{ display: 'flex' }}>
            <button
              type="button"
              onClick={() => onAnswer(option.id)}
              disabled={busy}
              style={{
                flex: 1,
                minHeight: 44,
                textAlign: 'left',
                background: 'var(--canvas)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)',
                color: 'var(--ink)',
                padding: '14px 16px',
                fontFamily: 'var(--font-sans)',
                fontSize: 15,
                cursor: busy ? 'not-allowed' : 'pointer',
                opacity: busy ? 0.55 : 1,
                transition: 'background var(--dur-fast) var(--ease-standard)',
              }}
            >
              {option.label}
            </button>
          </li>
        ))}
      </ul>

      <div>
        <Button variant="ghost" size="sm" onClick={() => onAnswer(null)} disabled={busy}>
          {question.skip_label}
        </Button>
      </div>
    </section>
  )
}
