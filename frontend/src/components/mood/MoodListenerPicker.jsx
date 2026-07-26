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
 * Layout: a compact native <select> holds every listener (so the control stays
 * small however many there are and stays keyboard-navigable with type-ahead),
 * and the chosen person's characteristics sit ALONGSIDE it — pick on the left,
 * read who they are on the right.
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

  const selected = profiles.find((p) => p.persona_id === value) || null;

  return (
    <fieldset
      style={{
        border: "none",
        padding: 0,
        margin: 0,
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}
    >
      <legend
        className="label-upper"
        style={{ fontSize: 11, padding: 0, marginBottom: 2 }}
      >
        Listening as
      </legend>

      <div
        style={{
          display: "flex",
          gap: 24,
          alignItems: "flex-start",
          flexWrap: "wrap",
        }}
      >
        {/* Left — the dropdown holding every listener. */}
        <div style={{ display: "flex", flexDirection: "column", gap: 6, flex: "0 0 auto" }}>
          <label htmlFor="mood-listener" style={{ fontSize: 12.5, color: "var(--muted)" }}>
            Choose a listener
          </label>
          <div style={{ position: "relative", width: 260, maxWidth: "100%" }}>
            <select
              id="mood-listener"
              value={value ?? ""}
              disabled={disabled}
              onChange={(e) => onChange(e.target.value || null)}
              style={{
                width: "100%",
                minHeight: 44,
                appearance: "none",
                WebkitAppearance: "none",
                MozAppearance: "none",
                background: "var(--canvas)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
                color: "var(--ink)",
                padding: "0 38px 0 14px",
                fontFamily: "var(--font-sans)",
                fontSize: 15,
                lineHeight: 1.2,
                cursor: disabled ? "not-allowed" : "pointer",
                opacity: disabled ? 0.55 : 1,
              }}
            >
              <option value="">Anyone — no history</option>
              {profiles.map((p) => (
                <option key={p.persona_id} value={p.persona_id}>
                  {p.display_name} · {formatSlot(p.slot)}
                </option>
              ))}
            </select>
            {/* Custom caret — the native one clashes with the flat surfaces. */}
            <span
              aria-hidden="true"
              style={{
                position: "absolute",
                right: 14,
                top: "50%",
                transform: "translateY(-50%)",
                pointerEvents: "none",
                color: "var(--muted)",
                fontSize: 11,
              }}
            >
              ▾
            </span>
          </div>
        </div>

        {/* Right — the selected listener's description, parallel to the picker. */}
        <div style={{ flex: "1 1 300px", minWidth: 260, maxWidth: 560 }}>
          {selected ? (
            <ListenerCard profile={selected} />
          ) : (
            <div
              style={{
                border: "1px dashed var(--border)",
                borderRadius: "var(--radius-md)",
                padding: "14px 16px",
              }}
            >
              <p style={{ margin: 0, fontSize: 13, lineHeight: 1.55, color: "var(--muted)" }}>
                <strong style={{ color: "var(--ink)" }}>Anyone</strong> — no
                listening history, so results are a pure match on the feeling you
                typed. Pick a named listener to see how their taste re-ranks the
                same query.
              </p>
            </div>
          )}
        </div>
      </div>
    </fieldset>
  );
}
