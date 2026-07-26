/**
 * Mood-First Search — app shell.
 *
 * TWO STRUCTURAL RULES, both easy to get wrong:
 *
 * 1. SearchResponse.mode is NOT navigation. `empty | clarify | shelves |
 *    safety` are four states of ONE surface. They share a route, a URL and a
 *    back-button meaning. Route them separately and the flow becomes a wizard
 *    — back from shelves lands on the question again, which reads as the app
 *    not having heard you. Modes live in component state; tabs live in the
 *    router.
 *
 * 2. No browse tab. Ever. The PRD's first principle is that there is no genre
 *    fallback in the primary flow, and a nav bar is precisely the mechanism
 *    that smuggles one back in. Three tabs, each of which has to justify
 *    itself, plus a hidden dev tab for the genre-baseline comparison — which
 *    is a demo artifact, not a feature.
 *
 * Visual direction: the app is opened at 10:40pm, alone, in bed, by someone
 * whose eyes are dark-adapted. So it is dim on purpose — deep indigo rather
 * than black (black + a bright accent is a glare sandwich), and a warm sodium
 * amber for the one accent, the colour of an Indian street lamp through rain.
 * The signature is the active tab's glow: light bleeding upward, not a pill.
 */

import { useEffect, useState } from "react";
import * as api from "./api";
import EpisodeList from "./EpisodeList";
import LabPanel from "./LabPanel";
import {
  IconRipple,
  IconPlayerPlay,
  IconBookmark,
  IconFlask,
} from "@tabler/icons-react";

export const TOKENS = {
  ink: "#0E1220",
  inkRaised: "#161B2E",
  haze: "#2A3350",
  text: "#E6E4DD",
  muted: "#8A90A6",
  sodium: "#E8A54B",
};

/** Single source of truth. Tests and the dev tab read this too. */
export const NAV = [
  {
    id: "feel",
    label: "Feel",
    icon: IconRipple,
    hidden: false,
    // The four states this one tab contains.
    modes: ["empty", "clarify", "shelves", "safety"],
  },
  { id: "playing", label: "Playing", icon: IconPlayerPlay, hidden: false },
  { id: "yours", label: "Yours", icon: IconBookmark, hidden: false },
  { id: "lab", label: "Lab", icon: IconFlask, hidden: true },
];



/* ------------------------------------------------------------------ */

function TabButton({ tab, active, onSelect }) {
  const Icon = tab.icon;
  return (
    <button
      onClick={() => onSelect(tab.id)}
      aria-current={active ? "page" : undefined}
      aria-label={tab.label}
      style={{
        position: "relative",
        flex: tab.hidden ? "0 0 44px" : 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 4,
        padding: "10px 4px 14px",
        border: "none",
        background: "none",
        color: active ? TOKENS.sodium : TOKENS.muted,
        fontSize: 11,
        letterSpacing: "0.02em",
        cursor: "pointer",
        transition: "color 220ms ease",
      }}
    >
      {/* Signature: sodium light bleeding upward from the active tab.
          Not a pill, not an underline — the thing a lamp actually does. */}
      <span
        aria-hidden
        style={{
          position: "absolute",
          bottom: 0,
          left: "50%",
          transform: "translateX(-50%)",
          width: 64,
          height: 34,
          pointerEvents: "none",
          opacity: active ? 1 : 0,
          transition: "opacity 300ms ease",
          background: `radial-gradient(ellipse at 50% 100%, ${TOKENS.sodium}38 0%, transparent 70%)`,
        }}
      />
      <Icon size={20} stroke={1.5} />
      {!tab.hidden && <span>{tab.label}</span>}
    </button>
  );
}

export function TabBar({ active, onSelect, devMode }) {
  const tabs = NAV.filter((t) => !t.hidden || devMode);
  return (
    <nav
      style={{
        display: "flex",
        alignItems: "stretch",
        borderTop: `1px solid ${TOKENS.haze}`,
        background: TOKENS.inkRaised,
        paddingBottom: "env(safe-area-inset-bottom)",
      }}
    >
      {tabs.map((tab) => (
        <TabButton
          key={tab.id}
          tab={tab}
          active={active === tab.id}
          onSelect={onSelect}
        />
      ))}
    </nav>
  );
}

/* ------------------------------------------------------------------ */

/**
 * The Feel surface. One component, four modes.
 *
 * `mode` comes straight off SearchResponse.mode — the frontend never decides
 * which screen to show, the contract does. If a fifth mode is ever added, the
 * only change here is a branch.
 */
function FeelSurface({
  state, onSearch, onAnswer, onRefine, profileId, onProfile, onOpen,
}) {
  const { mode, data } = state;

  // The bar is hidden on the safety screen. Someone in crisis does not get a
  // row of demo controls above the one thing that matters.
  const bar =
    mode === "safety" ? null : (
      <PersonaBar selected={profileId} onSelect={onProfile} />
    );

  const body = (() => {
    if (mode === "clarify")
      return <Clarify question={data.clarifying_question} onAnswer={onAnswer} />;
    if (mode === "shelves")
      return (
        <Shelves shelves={data.shelves} onRefine={onRefine} onOpen={onOpen} />
      );
    return <Starters onPick={onSearch} />;
  })();

  if (mode === "safety") {
    return (
      <Safety message={data.safety_message} resources={data.support_resources} />
    );
  }

  return (
    <>
      {bar}
      {body}
    </>
  );
}

/**
 * Listener picker.
 *
 * DEMO AFFORDANCE, NOT A PRODUCT SURFACE. Real listeners never choose who they
 * are — in production the profile comes from auth and this bar does not exist.
 * It sits inline rather than on its own screen for one reason: a separate
 * picker forces you to retype the query for each listener, which destroys the
 * only comparison worth showing. Type once, switch listener, watch the shelves
 * move.
 */
function PersonaBar({ selected, onSelect }) {
  const [profiles, setProfiles] = useState([]);

  useEffect(() => {
    api.getProfiles().then((d) => setProfiles(d.profiles)).catch(() => setProfiles([]));
  }, []);

  if (!profiles.length) return null;

  const chip = (id, label, sub) => {
    const on = selected === id;
    return (
      <button
        key={id ?? "anon"}
        onClick={() => onSelect(id)}
        aria-pressed={on}
        style={{
          flex: "0 0 auto",
          background: on ? `${TOKENS.sodium}1A` : "transparent",
          border: `1px solid ${on ? TOKENS.sodium : TOKENS.haze}`,
          borderRadius: 999,
          color: on ? TOKENS.sodium : TOKENS.muted,
          padding: "7px 13px",
          fontSize: 12.5,
          lineHeight: 1.25,
          textAlign: "left",
          cursor: "pointer",
        }}
      >
        <div>{label}</div>
        {sub && (
          <div style={{ fontSize: 10.5, opacity: 0.75, marginTop: 1 }}>{sub}</div>
        )}
      </button>
    );
  };

  return (
    <div
      style={{
        display: "flex",
        gap: 8,
        overflowX: "auto",
        padding: "12px 20px",
        borderBottom: `1px solid ${TOKENS.haze}`,
      }}
    >
      {chip(null, "Anyone", "no history")}
      {profiles.map((p) =>
        chip(p.persona_id, p.display_name, `${p.slot} · ${p.history_count} watched`)
      )}
    </div>
  );
}

function Starters({ onPick }) {
  const [starters, setStarters] = useState([]);
  const [text, setText] = useState("");

  useEffect(() => {
    api.getStarters().then((d) => setStarters(d.starters)).catch(() => setStarters([]));
  }, []);

  return (
    <div style={{ padding: "28px 20px" }}>
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && text.trim() && onPick(text)}
        placeholder="How do you want this to feel?"
        style={{
          width: "100%",
          background: "transparent",
          border: "none",
          borderBottom: `1px solid ${TOKENS.haze}`,
          color: TOKENS.text,
          fontSize: 17,
          padding: "10px 0 14px",
          outline: "none",
        }}
      />
      {/* Queries, not shows. A grid of titles here would quietly reinstate
          the browse experience this product exists to replace. */}
      <div style={{ marginTop: 26, display: "grid", gap: 10 }}>
        {starters.map((s) => (
          <button
            key={s.id}
            onClick={() => onPick(s.text)}
            style={{
              textAlign: "left",
              background: TOKENS.inkRaised,
              border: `1px solid ${TOKENS.haze}`,
              borderRadius: 12,
              color: TOKENS.text,
              padding: "13px 15px",
              fontSize: 14,
              lineHeight: 1.5,
              cursor: "pointer",
            }}
          >
            {s.text}
          </button>
        ))}
      </div>
    </div>
  );
}

function Clarify({ question, onAnswer }) {
  return (
    <div style={{ padding: "32px 20px" }}>
      <p style={{ fontSize: 19, color: TOKENS.text, margin: "0 0 22px" }}>
        {question.question}
      </p>
      <div style={{ display: "grid", gap: 10 }}>
        {question.options.map((o) => (
          <button
            key={o.id}
            onClick={() => onAnswer(o.id)}
            style={{
              textAlign: "left",
              background: "transparent",
              border: `1px solid ${TOKENS.sodium}55`,
              borderRadius: 12,
              color: TOKENS.text,
              padding: "13px 15px",
              fontSize: 15,
              cursor: "pointer",
            }}
          >
            {o.label}
          </button>
        ))}
      </div>
      <button
        onClick={() => onAnswer(null)}
        style={{
          marginTop: 18,
          background: "none",
          border: "none",
          color: TOKENS.muted,
          fontSize: 13,
          cursor: "pointer",
        }}
      >
        {question.skip_label}
      </button>
    </div>
  );
}

function Shelves({ shelves, onRefine, onOpen }) {
  return (
    <div style={{ padding: "20px 0 8px" }}>
      {shelves.map((shelf) => (
        <section key={shelf.id} style={{ marginBottom: 30 }}>
          <header style={{ padding: "0 20px 10px" }}>
            <h2 style={{ fontSize: 16, color: TOKENS.text, margin: 0 }}>
              {shelf.label}
            </h2>
            <p style={{ fontSize: 13, color: TOKENS.muted, margin: "3px 0 0" }}>
              {shelf.subtitle}
            </p>
          </header>
          <div style={{ display: "grid", gap: 8, padding: "0 20px" }}>
            {shelf.results.map((r) => (
              <article
                key={r.content_id}
                onClick={() => onOpen(r)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && onOpen(r)}
                style={{
                  background: TOKENS.inkRaised,
                  border: `1px solid ${TOKENS.haze}`,
                  borderRadius: 12,
                  padding: "13px 15px",
                  cursor: "pointer",
                }}
              >
                <div style={{ fontSize: 15, color: TOKENS.text }}>
                  {r.series_title}
                </div>
                <div
                  style={{ fontSize: 12, color: TOKENS.sodium, marginTop: 3 }}
                >
                  {r.entry_label}
                </div>
                {/* The line people quote. Give it room. */}
                <p
                  style={{
                    fontSize: 13.5,
                    color: TOKENS.muted,
                    lineHeight: 1.55,
                    margin: "9px 0 0",
                  }}
                >
                  {r.explanation}
                </p>
              </article>
            ))}
          </div>
          <RefineRow shelf={shelf} onRefine={onRefine} />
        </section>
      ))}
    </div>
  );
}

/**
 * Sliders send raw positions, never pre-nudged axes — the engine needs to know
 * WHICH axis was steered to grant it filter room. Sending only the destination
 * point makes the drag a no-op; that bug already happened once.
 */
function RefineRow({ shelf, onRefine }) {
  const [sliders, setSliders] = useState([]);
  useEffect(() => {
    api.getSliders().then((d) => setSliders(d.sliders)).catch(() => setSliders([]));
  }, []);

  return (
    <div
      style={{
        display: "flex",
        gap: 8,
        overflowX: "auto",
        padding: "12px 20px 0",
      }}
    >
      {sliders.map((s) => (
        <div key={s.id} style={{ display: "flex", gap: 6 }}>
          {[
            [-1, s.left],
            [1, s.right],
          ].map(([v, label]) => (
            <button
              key={label}
              onClick={() => onRefine(shelf, { [s.id]: v })}
              style={{
                whiteSpace: "nowrap",
                background: "transparent",
                border: `1px solid ${TOKENS.haze}`,
                borderRadius: 999,
                color: TOKENS.muted,
                fontSize: 12.5,
                padding: "6px 12px",
                cursor: "pointer",
              }}
            >
              {label}
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}

function Safety({ message, resources }) {
  return (
    <div style={{ padding: "40px 22px" }}>
      <p style={{ fontSize: 17, color: TOKENS.text, lineHeight: 1.65 }}>
        {message}
      </p>
      <div style={{ marginTop: 22, display: "grid", gap: 8 }}>
        {resources.map((r) => (
          <div key={r} style={{ fontSize: 14, color: TOKENS.sodium }}>
            {r}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */

export default function AppShell({ tab: initialTab = "feel", onNavigate }) {
  const [tab, setTab] = useState(initialTab);
  const [devMode, setDevMode] = useState(false);
  const [state, setState] = useState({ mode: "empty", data: null });
  const [queryId, setQueryId] = useState(null);
  const [profileId, setProfileId] = useState(null);
  const [lastText, setLastText] = useState("");
  const [playing, setPlaying] = useState(null);

  useEffect(() => {
    setDevMode(new URLSearchParams(window.location.search).has("dev"));
  }, []);

  async function onSearch(text) {
    setLastText(text);
    const data = await api.search(text, profileId);
    setQueryId(data.query_id);
    setState({ mode: data.mode, data });
  }

  /**
   * Switching listener re-runs the SAME query rather than clearing the screen.
   * That is the entire demo beat — if picking a listener reset you to the
   * empty state, there would be nothing to compare against.
   */
  async function onProfile(nextId) {
    setProfileId(nextId);
    if (!lastText) return;
    const data = await api.search(lastText, nextId);
    setQueryId(data.query_id);
    setState({ mode: data.mode, data });
  }

  async function onAnswer(optionId) {
    const data = await api.answerClarify(queryId, optionId);
    setState({ mode: data.mode, data });
  }

  async function onRefine(shelf, sliderDeltas) {
    const data = await api.refineShelf(
      queryId, shelf.id, shelf.target_axes, sliderDeltas
    );
    // Replace only the shelf that moved. Re-rendering all three makes a nudge
    // look like a new search.
    setState((prev) => ({
      mode: "shelves",
      data: {
        ...prev.data,
        shelves: prev.data.shelves.map((s) =>
          s.id === shelf.id ? data.shelves[0] : s
        ),
      },
    }));
  }

  /**
   * Tab changes are local state by default. If the host app has a router,
   * pass `onNavigate` and it will be called with the tab id instead — this
   * component should not reach for window.history and guess at your routes.
   */
  function go(next) {
    setTab(next);
    if (onNavigate) onNavigate(next);
  }

  /**
   * Card tap -> the episode fetch. `series_id` comes off the card rather than
   * being carved out of `content_id`, which is an arc id and was never
   * promised to encode the series.
   */
  function onOpen(card) {
    setPlaying({
      seriesId: card.series_id,
      seriesTitle: card.series_title,
      entryEpisode: card.entry_episode,
      entryLabel: card.entry_label,
    });
    go("playing");
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        minHeight: "100dvh",
        background: TOKENS.ink,
        color: TOKENS.text,
        fontFamily: "system-ui, -apple-system, sans-serif",
      }}
    >
      <main style={{ flex: 1, overflowY: "auto" }}>
        {tab === "feel" && (
          <FeelSurface
            state={state}
            onSearch={onSearch}
            onAnswer={onAnswer}
            onRefine={onRefine}
            profileId={profileId}
            onProfile={onProfile}
            onOpen={onOpen}
          />
        )}
        {tab === "playing" && (
          <EpisodeList
            tokens={TOKENS}
            playing={playing}
            onBack={() => go("feel")}
          />
        )}
        {tab === "yours" && <Placeholder label="Saved shows land here" />}
        {tab === "lab" && (
          <LabPanel tokens={TOKENS} queryId={queryId} lastText={lastText} />
        )}
      </main>
      <TabBar active={tab} onSelect={go} devMode={devMode} />
    </div>
  );
}

function Placeholder({ label }) {
  return (
    <div style={{ padding: "60px 22px", color: TOKENS.muted, fontSize: 14 }}>
      {label}
    </div>
  );
}
