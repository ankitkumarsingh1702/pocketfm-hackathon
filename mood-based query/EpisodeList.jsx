/**
 * Episode list — the GET touchpoint.
 *
 * Fetches GET /episodes/{series_id}?start={entry_episode}, i.e. the window
 * that begins at the doorway the shelf promised. Not episode 1.
 *
 * That default is the whole point of arc-level indexing surviving into the
 * UI. If tapping "Start at Ep 34" dropped you at the top of a 212-episode
 * list, the recommendation would have been reduced back to a series title in
 * the last inch of the journey.
 *
 * Episodes before the entry point are still reachable — "Earlier episodes"
 * refetches from 1 — they are just not what you land on.
 */

import { useCallback, useEffect, useState } from "react";

import * as api from "./api";

function mmss(seconds) {
  const m = Math.floor(seconds / 60);
  return `${m} min`;
}

export default function EpisodeList({ tokens, playing, onBack }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [start, setStart] = useState(playing?.entryEpisode ?? 1);

  useEffect(() => {
    setStart(playing?.entryEpisode ?? 1);
  }, [playing?.seriesId, playing?.entryEpisode]);

  const load = useCallback(
    async (from) => {
      if (!playing?.seriesId) return;
      setLoading(true);
      setError(null);
      try {
        const json = await api.getEpisodes(playing.seriesId, from, 12);
        if (json.error) setError(json.error);
        else setData(json);
      } catch (e) {
        setError("Couldn't reach the catalog. Retry.");
      } finally {
        setLoading(false);
      }
    },
    [playing?.seriesId]
  );

  useEffect(() => {
    load(start);
  }, [load, start]);

  if (!playing?.seriesId) {
    return (
      <div style={{ padding: "60px 22px", color: tokens.muted, fontSize: 14 }}>
        Nothing playing yet. Pick something from a shelf.
      </div>
    );
  }

  return (
    <div style={{ padding: "18px 20px" }}>
      <button
        onClick={onBack}
        style={{
          background: "none",
          border: "none",
          color: tokens.muted,
          fontSize: 13,
          padding: 0,
          marginBottom: 14,
          cursor: "pointer",
        }}
      >
        ← Back to shelves
      </button>

      <h1 style={{ fontSize: 20, color: tokens.text, margin: "0 0 4px" }}>
        {data?.series_title || playing.seriesTitle}
      </h1>
      <div style={{ fontSize: 12.5, color: tokens.sodium, marginBottom: 18 }}>
        {playing.entryLabel}
      </div>

      {loading && (
        <div style={{ fontSize: 13, color: tokens.muted }}>Loading episodes…</div>
      )}

      {error && (
        <div style={{ fontSize: 13, color: "#C97070" }}>
          {error}{" "}
          <button
            onClick={() => load(start)}
            style={{
              background: "none",
              border: "none",
              color: tokens.sodium,
              fontSize: 13,
              cursor: "pointer",
            }}
          >
            Retry
          </button>
        </div>
      )}

      {data && (
        <>
          {start > 1 && (
            <button
              onClick={() => setStart(1)}
              style={{
                width: "100%",
                background: "transparent",
                border: `1px solid ${tokens.haze}`,
                borderRadius: 10,
                color: tokens.muted,
                padding: "9px 12px",
                fontSize: 12.5,
                marginBottom: 10,
                cursor: "pointer",
              }}
            >
              Earlier episodes (1–{start - 1})
            </button>
          )}

          <div style={{ display: "grid", gap: 7 }}>
            {data.episodes.map((ep) => (
              <div
                key={ep.number}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  background: tokens.inkRaised,
                  border: `1px solid ${
                    ep.is_arc_start ? `${tokens.sodium}66` : tokens.haze
                  }`,
                  borderRadius: 10,
                  padding: "11px 13px",
                }}
              >
                <div
                  style={{
                    fontSize: 12,
                    color: ep.is_arc_start ? tokens.sodium : tokens.muted,
                    minWidth: 30,
                  }}
                >
                  {ep.number}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 14, color: tokens.text }}>
                    {ep.title}
                  </div>
                  <div style={{ fontSize: 11.5, color: tokens.muted, marginTop: 2 }}>
                    {mmss(ep.duration_sec)}
                    {ep.is_arc_start ? " · arc starts here" : ""}
                  </div>
                </div>
                {/* A missing file is a content gap, not a reason to hide the
                    episode. Show it, disable play, say why. */}
                <button
                  disabled={!ep.audio_url}
                  title={ep.audio_url ? "Play" : "No audio in this catalog"}
                  style={{
                    background: "transparent",
                    border: `1px solid ${
                      ep.audio_url ? tokens.sodium : tokens.haze
                    }`,
                    borderRadius: 999,
                    color: ep.audio_url ? tokens.sodium : tokens.muted,
                    fontSize: 12,
                    padding: "5px 12px",
                    cursor: ep.audio_url ? "pointer" : "not-allowed",
                  }}
                >
                  {ep.audio_url ? "Play" : "—"}
                </button>
              </div>
            ))}
          </div>

          {data.has_more && (
            <button
              onClick={() =>
                setStart(data.episodes[data.episodes.length - 1].number + 1)
              }
              style={{
                width: "100%",
                background: "transparent",
                border: `1px solid ${tokens.haze}`,
                borderRadius: 10,
                color: tokens.muted,
                padding: "9px 12px",
                fontSize: 12.5,
                marginTop: 10,
                cursor: "pointer",
              }}
            >
              More episodes ({data.total - data.episodes.slice(-1)[0].number} left)
            </button>
          )}
        </>
      )}
    </div>
  );
}
