import { useState } from 'react'

/**
 * The Genre Converter pipeline as an interactive flowchart.
 *
 * A vertical flow of nodes joined by labelled arrows — the labels are the
 * artifacts that actually travel between stages. Every node expands into
 * "what happens", "why this way", and an example; the examples follow one
 * beat (a hidden confession letter) through the whole pipeline, so a reader
 * can watch a single plot moment survive the trip.
 */

const CHIP_STYLE = {
  model: { background: 'var(--accent-soft)', border: 'var(--accent-line)', color: 'var(--accent-text-sm)' },
  free: { background: 'var(--surface)', border: 'var(--border)', color: 'var(--muted)' },
  io: { background: 'var(--canvas)', border: 'var(--ink)', color: 'var(--ink)' },
}

const STEPS = [
  {
    id: 'input',
    kind: 'io',
    chip: 'input',
    title: 'Your story goes in',
    summary: 'Pasted or uploaded as .txt, with a target genre.',
    what:
      'The service checks the basics before spending anything: at least 400 characters (shorter has no plot to extract), at most 60,000 (longer needs a different pipeline), and a known genre pack. It hashes the text — the same story is never paid for twice, which is why a repeat run finishes in seconds.',
    why:
      'Everything after this point costs model calls and minutes. Rejecting impossible input up front, with a specific message, is cheaper than failing five minutes in.',
    example:
      'Our running example: a family drama containing the moment — "Sunita finds her brother\'s unsent confession letter in the attic and hides it from the family." Watch that one beat travel through every step below.',
  },
  {
    id: 'extract',
    kind: 'model',
    chip: 'Gemini call',
    title: 'Extract the plot skeleton',
    summary: 'The plot is pulled out; everything the genre owns is thrown away.',
    what:
      'One model call reads the whole story and produces a skeleton: a one-line logline, each character reduced to a function (protagonist, gatekeeper, betrayer…), and the story cut into 8–15 beats — who acts, what happens, the outcome (success / failure / reversal / reveal), which later beats it causes, and whether it is load-bearing (deleting it would change the ending; most stories have 3–6 of these).',
    why:
      'Whatever stays in the skeleton is something the rewrite is NOT allowed to change. So the rules are brutal: no names, no genre words, no sensory detail. A beat should read like a line from a court transcript — that flatness is what leaves the new genre free to reinvent every surface.',
    example:
      '"Sunita finds her brother\'s unsent confession letter and hides it" becomes:\n\nb6 · confidant — "the confidant discovers withheld information and conceals it from the group" · [reveal] · causes b9 · LOAD-BEARING\n\nNo Sunita, no attic, no letter — just the move.',
  },
  {
    id: 'lint',
    kind: 'free',
    chip: 'no tokens · pure code',
    title: 'Lint the skeleton for leaks',
    summary: 'A free scan for smuggled names and genre words.',
    loop: '↺ if it finds leaks, the extractor is re-asked once — same beats, cleaner wording',
    what:
      'Plain Python scans every field for two failure modes: character names that slipped through, and genre-loaded vocabulary ("dread", "tender", "hilarious"…). It also sanity-checks structure — every beat\'s actor must exist in the roles list, every "causes" id must exist, at least one beat must be load-bearing.',
    why:
      'If the skeleton is already flavoured, the transform cannot move the story far — a leaked "dread" pins the rewrite to horror no matter what genre you asked for. Catching that costs zero tokens here and a ruined rewrite later.',
    example:
      'Complaint: beat b6 action contains the character name \'Sunita\'. The extractor redoes the wording only — same beats, same ids, same flags. If you pressed "Extract skeleton only", the job ends here (~20 seconds).',
  },
  {
    id: 'plan',
    kind: 'free',
    chip: 'no tokens · deterministic',
    title: 'Plan the scenes',
    summary: 'Beats are grouped into scenes by a fixed rule, before any writing.',
    what:
      'Consecutive beats are grouped — at most three per scene, and the group always cuts immediately after a load-bearing beat. Pure arithmetic, no model, so the total scene count is known before the first word is written.',
    why:
      'A scene asked to land two pivotal moments will short-change one of them — and the one it short-changes is exactly what the verifier will flag. One pivot per scene, maximum. Knowing the scene count up front is also what makes the progress bar honest instead of a guess.',
    example:
      '12 beats with pivots at b3, b6, and b11 plan into five scenes: [b1 b2 b3] [b4 b5 b6] [b7 b8 b9] [b10 b11] [b12]. Our b6 closes scene 2 — it gets a scene ending all to itself.',
  },
  {
    id: 'write',
    kind: 'model',
    chip: 'Gemini call × N scenes',
    title: 'Write each scene in the new genre',
    summary: 'One call per scene. The writer never sees your original story.',
    what:
      'Each call receives exactly three things: the genre pack (premise, pacing, dialogue register, the moves readers expect, and the taboo moves that would break the genre), the 1–3 beats this scene owns, and a two-sentence rolling summary written by the previous scene\'s call — names invented so far, where we are, what just changed. The final scene is told: "the story ends here — land it."',
    why:
      'A single "rewrite this whole story as horror" call quietly loses beats from the middle — the model optimises the prose in front of it. Small scenes with explicit duties don\'t get that chance. And hiding the source text means there is no surface detail to copy: the genre must reinvent everything, because the skeleton gives it nothing else.',
    example:
      'The same b6, two genres:\n\nhorror — "The letter was nailed shut behind the attic beam, and Mira understood, resealing it, that some confessions are kept the way graves are kept."\n\ncomedy — "Priya found the draft. Forty-seven versions of the same unsent text, each one worse. She did the only responsible thing: archive, airplane mode, denial."\n\nSame role, same concealment, same turn — different everything else.',
  },
  {
    id: 'retry',
    kind: 'free',
    chip: 'self-check per scene',
    title: 'Check the scene delivered its beats',
    summary: 'Each scene reports what it put on the page; a dropped pivot gets one retry.',
    loop: '↺ a missing load-bearing beat sends the scene back once, with the beat quoted',
    what:
      'Every scene call also reports which beat ids it actually dramatised. If a load-bearing beat is missing from that report, the scene is rewritten once — same setting, same names, same voice — with the missing beat quoted back and an instruction to make it happen on the page rather than being alluded to. Supporting beats are not worth a retry\'s wall-clock; the verifier will report them anyway.',
    why:
      'Fixing a dropped pivot costs one scene now, or a whole re-run after the story is finished. Catching it while the scene is still on the bench is the cheap moment.',
    example:
      'Scene 2\'s report omits b6 → retry prompt: "MISSING — b6: the confidant discovers withheld information and conceals it from the group. Write the scene again…"',
  },
  {
    id: 'verify',
    kind: 'model',
    chip: 'Gemini call × 6, concurrent',
    title: 'Verify with six independent judges',
    summary: 'Cold readers check the finished prose against your story\'s skeleton.',
    what:
      'Three "delivery" ballots each read the full rewrite and answer, per source beat: does this actually HAPPEN on the page? Three "link" ballots answer, per causal edge: does the second thing still visibly happen because of the first? A majority vote (2 of 3) merges each set. The judges score function, not costume — but they are strict: recollection is not occurrence, foreshadowing doesn\'t count, the wrong actor doesn\'t count, an inverted outcome fails.',
    why:
      'The writer grading its own homework failed confidently in testing — and a single judgement call isn\'t reproducible either (the same comparison once scored 68% and 93% on separate runs). Independent cold reads plus voting turn a shaky instrument into a stable number.',
    example:
      'If the rewrite only says "Mira remembered hiding the letter years ago" — verdict: NOT delivered ("recollection is not occurrence"), vote 0/3. If she hides it on the page in scene 2 — delivered, 3/3.',
  },
  {
    id: 'score',
    kind: 'free',
    chip: 'no tokens · arithmetic',
    title: 'Score the fidelity',
    summary: 'One reproducible number: how much of the plot survived.',
    what:
      'Deterministic math over the merged votes: 60% × load-bearing recall + 20% × all-beat recall + 20% × causal-edge recall. The report also names exactly which load-bearing beats never made the page (with the judges\' reasons) and which causal links broke — that is what the Fidelity tab shows.',
    why:
      'The weighting is the claim the tool actually makes: the beats the story collapses without matter most; the other two components stop a rewrite from scoring well by keeping the spine while shredding everything around it. And because the math is plain code, the same votes always give the same number.',
    example:
      '3 of 4 pivots + 4 of 5 beats + 4 of 4 links →  0.6×0.75 + 0.2×0.80 + 0.2×1.00 = 76%. Don\'t read it against 100%: even re-extracting the original story doesn\'t score perfect, so part of any gap is extractor noise, not plot damage.',
  },
  {
    id: 'history',
    kind: 'io',
    chip: 'output',
    title: 'Deliver and remember',
    summary: 'The rewrite, the score breakdown — and a history record.',
    what:
      'The job finishes with the rewritten story, its word count, the timing, and the full fidelity breakdown. The whole run — input story, skeleton, rewrite, scores — is saved to the service\'s history, keyed by story + genre, which is what the History tab lists.',
    why:
      'Re-converting the same story to the same genre refreshes one record instead of stacking duplicates, so history stays a comparison table: the same plot, told five ways, each with a number.',
    example:
      'Convert the same story to horror (86%) and comedy (72%), open History, and read why comedy lost 14 points — it\'s usually one pivot that refused to be funny.',
  },
]

/** What travels down each arrow, in order (one fewer than the nodes). */
const FLOWS = [
  'story text + genre',
  'skeleton (roles · beats · causes)',
  'clean skeleton',
  'scene plan',
  'scene prose, one by one',
  'finished rewrite',
  'merged verdicts',
  'fidelity + report',
]

function Chip({ kind, children }) {
  const s = CHIP_STYLE[kind] ?? CHIP_STYLE.free
  return (
    <span
      style={{
        fontSize: 10.5,
        fontWeight: 600,
        letterSpacing: '0.06em',
        textTransform: 'uppercase',
        padding: '3px 9px',
        borderRadius: 'var(--radius-pill)',
        background: s.background,
        border: `1px solid ${s.border}`,
        color: s.color,
        whiteSpace: 'nowrap',
        flexShrink: 0,
      }}
    >
      {children}
    </span>
  )
}

function Connector({ label }) {
  return (
    <div aria-hidden="true" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '2px 0 2px 22px' }}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 12 }}>
        <span style={{ width: 1, height: 14, background: 'var(--dim)' }} />
        <span style={{ color: 'var(--dim)', fontSize: 9, lineHeight: 1 }}>▼</span>
      </div>
      {label && (
        <span className="font-mono-num" style={{ fontSize: 11, color: 'var(--muted)' }}>
          {label}
        </span>
      )}
    </div>
  )
}

function Section({ label, children, mono = false }) {
  return (
    <div>
      <div className="label-upper" style={{ fontSize: 10, marginBottom: 4 }}>
        {label}
      </div>
      <p
        style={{
          margin: 0,
          fontSize: 13.5,
          lineHeight: 1.65,
          color: 'var(--ink)',
          whiteSpace: 'pre-wrap',
          fontFamily: mono ? 'var(--font-mono)' : 'var(--font-sans)',
          ...(mono ? { fontSize: 12.5, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '10px 12px' } : {}),
        }}
      >
        {children}
      </p>
    </div>
  )
}

function FlowNode({ step, open, onToggle }) {
  return (
    <div
      style={{
        border: `1px solid ${open ? 'var(--ink)' : 'var(--border)'}`,
        borderRadius: 'var(--radius-md)',
        background: 'var(--canvas)',
        overflow: 'hidden',
        transition: 'border-color var(--dur-fast) var(--ease-standard)',
      }}
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 6,
          width: '100%',
          textAlign: 'left',
          background: 'none',
          border: 'none',
          padding: '12px 14px',
          cursor: 'pointer',
        }}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%' }}>
          <span
            aria-hidden="true"
            style={{
              fontSize: 9,
              color: 'var(--muted)',
              transition: 'transform var(--dur-fast) var(--ease-standard)',
              transform: open ? 'rotate(90deg)' : 'none',
              flexShrink: 0,
            }}
          >
            ▶
          </span>
          <span style={{ fontSize: 14.5, fontWeight: 600, color: 'var(--ink)', flex: 1, minWidth: 0 }}>
            {step.title}
          </span>
          <Chip kind={step.kind}>{step.chip}</Chip>
        </span>
        <span style={{ fontSize: 12.5, color: 'var(--muted)', lineHeight: 1.5, paddingLeft: 19 }}>
          {step.summary}
        </span>
        {step.loop && (
          <span
            style={{
              alignSelf: 'flex-start',
              marginLeft: 19,
              fontSize: 11.5,
              color: 'var(--accent-text-sm)',
              border: '1px dashed var(--accent-line)',
              borderRadius: 'var(--radius-pill)',
              padding: '2px 10px',
            }}
          >
            {step.loop}
          </span>
        )}
      </button>

      {open && (
        <div
          style={{
            borderTop: '1px solid var(--border)',
            padding: '14px 14px 16px 33px',
            display: 'flex',
            flexDirection: 'column',
            gap: 14,
            background: 'var(--surface)',
          }}
        >
          <Section label="What happens">{step.what}</Section>
          <Section label="Why this way">{step.why}</Section>
          <Section label="Example" mono>
            {step.example}
          </Section>
        </div>
      )}
    </div>
  )
}

export default function PipelineExplainer() {
  const [openIds, setOpenIds] = useState(() => new Set(['extract']))

  const toggle = (id) =>
    setOpenIds((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      <p style={{ margin: '0 0 18px', fontSize: 13.5, lineHeight: 1.65, color: 'var(--muted)' }}>
        The converter pulls the plot out of your story, throws away everything else, rewrites
        that plot in the new genre one scene at a time, and then checks — beat by beat, with
        independent judges — how much of it survived. Tap any step for what it does, why it
        exists, and a worked example. A full run takes five to eight minutes; every red step
        is a model call, every grey one is free.
      </p>

      {STEPS.map((step, index) => (
        <div key={step.id}>
          <FlowNode step={step} open={openIds.has(step.id)} onToggle={() => toggle(step.id)} />
          {index < STEPS.length - 1 && <Connector label={FLOWS[index]} />}
        </div>
      ))}

      <p style={{ margin: '18px 0 0', fontSize: 12.5, lineHeight: 1.6, color: 'var(--dim)' }}>
        Repeat runs of the same story reuse the cached skeleton and rewrite, so they finish in
        seconds. The full write-up lives in the repo at
        backend/story-genre-convertor/HOW-IT-WORKS.md.
      </p>
    </div>
  )
}
