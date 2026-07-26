/**
 * Listener picker — a DEMO affordance, not a product surface.
 *
 * Real listeners never choose who they are; in production this comes from auth
 * and this control does not exist. It sits inline with the query rather than on
 * its own screen for one reason: a separate picker would force you to retype the
 * query for each listener, which destroys the only comparison worth showing —
 * type once, switch listener, watch the same query re-rank.
 *
 * Each option is a NAMED person, and selecting one reveals their characteristics
 * so the demo beat — "same query, different listener, different shelf" — is
 * legible: you can see WHY the ranking moved, not just that it did. The traits
 * shown are taste and habit (what they finish, when they listen), never mood:
 * the query is tonight, the listener is the last six months.
 *
 * A real radio group, so arrow keys move between listeners and the grouping is
 * announced. A row of buttons would lose both.
 */

const SLOT_LABEL = {
  late_night: "late nights",
  bedtime: "at bedtime",
  commute: "on the commute",
  chores: "during chores",
  work_break: "on work breaks",
};

const formatSlot = (slot) =>
  SLOT_LABEL[slot] || (slot ? slot.replace(/_/g, " ") : "anytime");

function heaviness(tolerance) {
  if (tolerance == null) return null;
  if (tolerance >= 0.66) return "high";
  if (tolerance >= 0.33) return "medium";
  return "low";
}

function Trait({ label, value }) {
  if (value == null || value === "") return null;
  return (
    <div
      style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}
    >
      <span
        className="label-upper"
        style={{ fontSize: 10, color: "var(--dim)" }}
      >
        {label}
      </span>
      <span style={{ fontSize: 13.5, color: "var(--ink)" }}>{value}</span>
    </div>
  );
}

/** The selected listener, laid out as a small "who they are" card. */
function ListenerCard({ profile }) {
  const pct =
    profile.completion_rate != null
      ? `${Math.round(profile.completion_rate * 100)}% of what they start`
      : null;
  const heavy = heaviness(profile.tolerance_for_heaviness);

  return (
    <div
      style={{
        border: "1px solid var(--accent-line)",
        background: "var(--accent-soft)",
        borderRadius: "var(--radius-md)",
        padding: "14px 16px",
        display: "flex",
        flexDirection: "column",
        gap: 12,
        maxWidth: 640,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: 10,
          flexWrap: "wrap",
        }}
      >
        <span style={{ fontSize: 16, fontWeight: 600, color: "var(--ink)" }}>
          {profile.display_name}
        </span>
        <span style={{ fontSize: 12.5, color: "var(--accent-text-sm)" }}>
          who they are — history only breaks ties
        </span>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
          gap: 14,
        }}
      >
        <Trait label="Listens" value={formatSlot(profile.slot)} />
        <Trait label="Finishes" value={pct} />
        <Trait
          label="Usually drifts off"
          value={
            profile.typical_dropoff_episode
              ? `around track ${profile.typical_dropoff_episode}`
              : null
          }
        />
        <Trait label="Tolerance for heavy" value={heavy} />
        <Trait
          label="Language"
          value={profile.language ? profile.language.toUpperCase() : null}
        />
        <Trait
          label="History"
          value={
            profile.history_count != null
              ? `${profile.history_count} in their lane`
              : null
          }
        />
      </div>

      {profile.finished?.length > 0 && (
        <p style={{ margin: 0, fontSize: 12.5, color: "var(--muted)" }}>
          {profile.finished.length} already-finished{" "}
          {profile.finished.length === 1 ? "series is" : "series are"} hidden
          from their results — finishing is not a request for more of it.
        </p>
      )}
    </div>
  );
}

export default function MoodListenerPicker({
  profiles,
  value,
  onChange,
  disabled = false,
}) {
  if (!profiles.length) return null;

  const options = [
    { id: null, label: "Anyone", sub: "no history" },
    ...profiles.map((p) => ({
      id: p.persona_id,
      label: p.display_name,
      sub: `${formatSlot(p.slot)} · ${p.history_count} watched`,
    })),
  ];

  const selected = profiles.find((p) => p.persona_id === value) || null;

  return (
    <fieldset
      style={{
        border: "none",
        display: "flex",
        flexDirection: "column",
        gap: 10,
      }}
    >
      <legend
        className="label-upper"
        style={{ fontSize: 11, marginBottom: 10 }}
      >
        Listening as
      </legend>
      {/* <p style={{ margin: 0, fontSize: 13, color: 'var(--muted)', maxWidth: '64ch' }}>
        A demo control. Pick a listener to see who they are — switching re-runs the
        same query, and history only breaks ties, never re-serving a series they
        already finished.
      </p> */}

      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {options.map((option) => {
          const isSelected = value === option.id;
          return (
            <label
              key={option.id ?? "anon"}
              style={{
                display: "inline-flex",
                flexDirection: "column",
                justifyContent: "center",
                minHeight: 44,
                padding: "6px 16px",
                borderRadius: "var(--radius-pill)",
                border: `1px solid ${isSelected ? "var(--accent-line)" : "var(--border)"}`,
                background: isSelected ? "var(--accent-soft)" : "var(--canvas)",
                color: isSelected ? "var(--accent-text-sm)" : "var(--ink)",
                cursor: disabled ? "not-allowed" : "pointer",
                opacity: disabled ? 0.55 : 1,
                transition: "background var(--dur-fast) var(--ease-standard)",
              }}
            >
              <input
                type="radio"
                name="mood-listener"
                checked={isSelected}
                disabled={disabled}
                onChange={() => onChange(option.id)}
                style={{
                  position: "absolute",
                  width: 1,
                  height: 1,
                  opacity: 0,
                  pointerEvents: "none",
                }}
              />
              <span
                style={{ fontSize: 14, fontWeight: isSelected ? 600 : 500 }}
              >
                {/* Selection is never carried by colour alone. */}
                <span
                  aria-hidden="true"
                  style={{ marginRight: 7, fontWeight: 700 }}
                >
                  {isSelected ? "✓" : "+"}
                </span>
                {option.label}
              </span>
              {option.sub && (
                <span style={{ fontSize: 11.5, opacity: 0.8, paddingLeft: 20 }}>
                  {option.sub}
                </span>
              )}
            </label>
          );
        })}
      </div>

      {/* The selected listener's characteristics, made explicit. */}
      {selected ? (
        <ListenerCard profile={selected} />
      ) : (
        <p
          style={{
            margin: "2px 0 0",
            fontSize: 12.5,
            color: "var(--dim)",
            maxWidth: "64ch",
          }}
        >
          <strong style={{ color: "var(--muted)" }}>Anyone</strong> — no
          listening history, so results are a pure match on the feeling you
          typed.
        </p>
      )}
    </fieldset>
  );
}
