/**
 * Lab — dev-only surface, reachable at ?dev=1.
 *
 * Holds the two things that must exist for the demo but must NOT be in the
 * user-facing nav:
 *
 *   1. The genre/keyword baseline, side by side with mood-first on the same
 *      query. Live, not a screenshot — it runs on whatever a judge types,
 *      which is the only version of this comparison worth showing. Shipping a
 *      genre search as a real tab would concede the argument the product
 *      exists to win.
 *
 *   2. /debug — what retrieval actually did. Blocked items, pool sizes,
 *      per-shelf latency. This is the tool for "why did that shelf come back
 *      thin", and it is where the contraindication layer becomes visible:
 *      the traps the baseline surfaces are the same rows this panel shows as
 *      blocked.
 */

import { useEffect, useState } from "react";

import * as api from "./api";

export default function LabPanel({ tokens, queryId, lastText }) {
  const [text, setText] = useState(lastText || "");
  const [baseline, setBaseline] = useState(null);
  const [mood, setMood] = useState(null);
  const [debug, setDebug] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!queryId) return;
    api.getDebug(queryId).then(setDebug).catch(() => setDebug(null));
  }, [queryId]);

  async function compare() {
    if (!text.trim()) return;
    setBusy(true);
    try {
      const [b, m] = await Promise.all([
        api.runBaseline(text, 3),
        api.search(text),
      ]);
      setBaseline(b.results || []);
      setMood(m.shelves || []);
    } finally {
      setBusy(false);
    }
  }

  const col = { flex: 1, minWidth: 0 };
  const head = {
    fontSize: 11,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    color: tokens.muted,
    marginBottom: 10,
  };

  return (
    <div style={{ padding: "20px", color: tokens.text }}>
      <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && compare()}
          placeholder="Same query, both systems"
          style={{
            flex: 1,
            background: tokens.inkRaised,
            border: `1px solid ${tokens.haze}`,
            borderRadius: 8,
            color: tokens.text,
            padding: "9px 12px",
            fontSize: 14,
            outline: "none",
          }}
        />
        <button
          onClick={compare}
          disabled={busy}
          style={{
            background: "transparent",
            border: `1px solid ${tokens.sodium}`,
            borderRadius: 8,
            color: tokens.sodium,
            padding: "9px 16px",
            fontSize: 13,
            cursor: "pointer",
          }}
        >
          {busy ? "…" : "Compare"}
        </button>
      </div>

      <div style={{ display: "flex", gap: 18, alignItems: "flex-start" }}>
        <div style={col}>
          <div style={head}>Genre / keyword search</div>
          {(baseline || []).map((h) => (
            <div
              key={h.content_id}
              style={{
                background: tokens.inkRaised,
                border: `1px solid ${h.is_trap ? "#8A3A3A" : tokens.haze}`,
                borderRadius: 10,
                padding: "10px 12px",
                marginBottom: 8,
              }}
            >
              <div style={{ fontSize: 13.5 }}>{h.series_title}</div>
              <div
                style={{
                  fontSize: 11.5,
                  color: tokens.muted,
                  marginTop: 4,
                  lineHeight: 1.45,
                }}
              >
                {h.snippet}
              </div>
              {h.is_trap && (
                <div style={{ fontSize: 11, color: "#C97070", marginTop: 6 }}>
                  contraindicated for this listener
                </div>
              )}
            </div>
          ))}
          {baseline && !baseline.length && (
            <div style={{ fontSize: 13, color: tokens.muted }}>No matches.</div>
          )}
        </div>

        <div style={col}>
          <div style={head}>Mood-first</div>
          {(mood || []).map((s) => (
            <div key={s.id} style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: tokens.sodium, marginBottom: 5 }}>
                {s.label}
              </div>
              {s.results.slice(0, 2).map((r) => (
                <div
                  key={r.content_id}
                  style={{
                    background: tokens.inkRaised,
                    border: `1px solid ${tokens.haze}`,
                    borderRadius: 10,
                    padding: "10px 12px",
                    marginBottom: 6,
                  }}
                >
                  <div style={{ fontSize: 13.5 }}>{r.series_title}</div>
                  <div style={{ fontSize: 11.5, color: tokens.muted, marginTop: 4 }}>
                    {r.entry_label}
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>

      {debug && (
        <div style={{ marginTop: 26 }}>
          <div style={head}>Retrieval trace</div>
          <div style={{ fontSize: 12.5, color: tokens.muted, lineHeight: 1.8 }}>
            <div>
              profile: {debug.profile || "anonymous"} · blocked by
              contraindication: {(debug.blocked || []).length}
            </div>
            {(debug.shelves || []).map((s) => (
              <div key={s.destination}>
                {s.destination}: pool {s.pool_size} · dropped{" "}
                {s.dropped_by_reranker} · entry swaps {s.entry_swaps} ·{" "}
                {s.latency_ms}ms
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
