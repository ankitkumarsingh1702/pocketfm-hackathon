/** Consistent page header for every lens: eyebrow, title, one-line purpose. */
export default function PageHeader({ lens }) {
  return (
    <header className="page-head">
      <div className="label-upper page-head__eyebrow" style={{ fontSize: 11 }}>
        Simulated Studio
      </div>
      <h1 className="page-head__title">{lens.title}</h1>
      <p className="page-head__blurb">{lens.blurb}</p>
    </header>
  )
}
