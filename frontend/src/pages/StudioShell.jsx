import { useEffect, useRef, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { DEFAULT_LENS_PATH, LENSES } from '../config/constants'
import { HINDI_STORY_LIBRARY } from '../config/hindiStories'
import { useStudio } from '../controllers/useStudio'
import { useStatusToast } from '../hooks/useStatusToast'
import { useToast } from '../components/toast/useToast'
import Sidebar from '../components/layout/Sidebar'
import PageHeader from '../components/layout/PageHeader'
import StoryInput from '../components/StoryInput'
import StoryPicker from '../components/StoryPicker'
import { Icon, Wordmark } from '../components/primitives'
import AgentDirectoryTab from '../components/tabs/AgentDirectoryTab'
import A2ATab from '../components/tabs/A2ATab'
import AudienceSimulatorTab from '../components/tabs/AudienceSimulatorTab'
import CliffhangerOptimizerTab from '../components/tabs/CliffhangerOptimizerTab'
import DbMemoryTab from '../components/tabs/DbMemoryTab'
import GenreConverterTab from '../components/tabs/GenreConverterTab'
import MoodSearchTab from '../components/tabs/MoodSearchTab'
import StoryCanonTab, { PlannerPanel } from '../components/tabs/StoryCanonTab'
import WritersRoom from '../WritersRoom'

const LENS_BY_PATH = new Map(LENSES.map((lens) => [lens.path, lens]))

/** `/audience/` and `/audience` are the same lens. */
function normalize(pathname) {
  return pathname.length > 1 && pathname.endsWith('/') ? pathname.slice(0, -1) : pathname
}

/**
 * The studio frame: sidebar navigation + the routed lens.
 *
 * Every lens panel stays mounted for the life of the app and is merely hidden
 * when its route is not active — so a five-minute genre conversion, a streaming
 * Writers Room run, or an edited roster survives switching lenses. The URL is
 * the single source of truth for which lens is showing, which is what makes a
 * reload land back on the same lens.
 *
 * All state, data fetching, and orchestration live in `useStudio` and the
 * self-contained lens components; this component only maps route + state onto
 * layout.
 */
export default function StudioShell() {
  const location = useLocation()
  const lens = LENS_BY_PATH.get(normalize(location.pathname))
  const activeTab = lens?.id ?? null

  const studio = useStudio(activeTab)
  const { story, setStory, run, isLoading, canRun } = studio

  const [navOpen, setNavOpen] = useState(false)
  const toast = useToast()

  // Every lens outcome — success or failure — is announced as a toast, so a
  // run that finishes while you are on another lens still tells you.
  useStatusToast(studio.health.error, (e) => toast.error(`Backend unreachable. ${e}`))

  // The Audience Simulator is self-contained (its own composer + live feed +
  // inline error surface), like the Writers Room and Genre Converter.

  useStatusToast(studio.cliffhanger.error, (e) =>
    toast.error(`Cliffhanger optimization failed. ${e}`),
  )
  useStatusToast(studio.cliffhanger.data, () => toast.success('Cliffhanger optimization finished.'))

  useStatusToast(studio.canon.ingestError, (e) => toast.error(`Canon ingest failed. ${e}`))
  useStatusToast(studio.canon.ingestResult, (r) =>
    toast.success(`Episode ingested — ${r.nodes_added} nodes, ${r.edges_added} edges added.`),
  )

  useStatusToast(studio.canon.plotHoles.error, (e) => toast.error(`Plot-hole scan failed. ${e}`))
  useStatusToast(studio.canon.plotHoles.data, (d) =>
    toast.success(
      d.isEmpty
        ? 'Plot-hole scan finished — no holes found.'
        : `Plot-hole scan finished — ${d.holes.length} found.`,
    ),
  )

  // The streaming panels settle when `running` flips off with results in hand.
  const { planner, agent, mdp } = studio.canon
  useStatusToast(planner.error, (e) => toast.error(`Cliffhanger search failed. ${e}`))
  useStatusToast(
    !planner.running && !planner.error && (planner.best || planner.candidates.length > 0)
      ? planner
      : null,
    () => toast.success('Cliffhanger search finished.'),
  )
  useStatusToast(agent.error, (e) => toast.error(`Showrunner agent failed. ${e}`))
  useStatusToast(agent.result, (r) =>
    toast.success(`Showrunner agent finished — hook ${r.before_score} → ${r.after_score}.`),
  )
  useStatusToast(mdp.error, (e) => toast.error(`Policy search failed. ${e}`))
  useStatusToast(!mdp.running && !mdp.error && mdp.final != null ? mdp : null, () =>
    toast.success('Policy search finished.'),
  )

  // DB / Memory polls every few seconds; latch by message so a down graph
  // reads as one notice, not one per poll. The page's inline error stays the
  // persistent signal.
  const dbErr =
    studio.dbMemory.activity.error ||
    studio.dbMemory.graph.error ||
    studio.dbMemory.facts.error ||
    null
  const dbErrShownRef = useRef(null)
  useEffect(() => {
    if (!dbErr || dbErr === dbErrShownRef.current) return
    dbErrShownRef.current = dbErr
    toast.error(`Shared-memory read failed. ${dbErr}`)
  }, [dbErr, toast])

  // The route names the lens; the tab title should agree with it.
  useEffect(() => {
    if (lens) document.title = `${lens.label} — Simulated Studio`
  }, [lens])

  // Arriving on a lens starts at its top, and closes the mobile drawer.
  useEffect(() => {
    setNavOpen(false)
    window.scrollTo(0, 0)
  }, [location.pathname])

  // While the drawer is open: lock the page scroll, let Escape dismiss it.
  useEffect(() => {
    if (!navOpen) return undefined
    document.body.style.overflow = 'hidden'
    const onKey = (event) => {
      if (event.key === 'Escape') setNavOpen(false)
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = ''
      document.removeEventListener('keydown', onKey)
    }
  }, [navOpen])

  if (!lens) return <Navigate to={DEFAULT_LENS_PATH} replace />

  const showStoryInput = activeTab === 'opt'

  return (
    <div className="shell">
      <a href="#main" className="skip-link">
        Skip to content
      </a>

      {/* Slim bar, small screens only — opens the navigation drawer. */}
      <header className="topbar">
        <button
          type="button"
          className="topbar__menu"
          onClick={() => setNavOpen(true)}
          aria-label="Open navigation"
          aria-expanded={navOpen}
        >
          <Icon name="menu" size={20} />
        </button>
        <Wordmark size={16} />
        <span className="topbar__spacer" />
      </header>

      {navOpen && (
        <button
          type="button"
          className="shell-scrim"
          aria-label="Close navigation"
          onClick={() => setNavOpen(false)}
        />
      )}

      <Sidebar open={navOpen} onNavigate={() => setNavOpen(false)} />

      <main id="main" className="content">
        <div className="content__inner">
          <PageHeader lens={lens} />

          {/* The Audience Simulator, Writers Room, Story Canon, DB / Memory, and
              Genre Converter lenses have their own composers, so the shared story
              input only shows for the Cliffhanger Optimizer, which runs from it. */}
          {showStoryInput && (
            <div style={{ marginBottom: 44 }}>
              <div style={{ marginBottom: 14 }}>
                <StoryPicker
                  onSelect={(s) => setStory(s.text)}
                  label="Load a ready-made story to optimize"
                  stories={HINDI_STORY_LIBRARY}
                />
              </div>
              <StoryInput
                value={story}
                onChange={setStory}
                onRun={run}
                loading={isLoading}
                canRun={canRun}
              />
            </div>
          )}

          <section className="lens-panel" hidden={activeTab !== 'agents'} aria-label="Agent Directory">
            <AgentDirectoryTab {...studio.agentDirectory} />
          </section>
          <section className="lens-panel" hidden={activeTab !== 'sim'} aria-label="Audience Simulator">
            <AudienceSimulatorTab />
          </section>
          <section className="lens-panel" hidden={activeTab !== 'a2a'} aria-label="A2A Word of Mouth">
            <A2ATab />
          </section>
          <section className="lens-panel" hidden={activeTab !== 'opt'} aria-label="Cliffhanger Optimizer">
            <CliffhangerOptimizerTab {...studio.cliffhanger} />
          </section>
          <section className="lens-panel" hidden={activeTab !== 'planner'} aria-label="Cliffhanger Planner">
            <PlannerPanel
              weakExcerpt={studio.canon.weakExcerpt}
              setWeakExcerpt={studio.canon.setWeakExcerpt}
              planner={studio.canon.planner}
              runPlanner={studio.canon.runPlanner}
              stopPlanner={studio.canon.stopPlanner}
            />
          </section>
          <section className="lens-panel" hidden={activeTab !== 'room'} aria-label="Writers Room">
            <WritersRoom />
          </section>
          <section className="lens-panel" hidden={activeTab !== 'canon'} aria-label="Story Canon">
            <StoryCanonTab {...studio.canon} />
          </section>
          <section className="lens-panel" hidden={activeTab !== 'db'} aria-label="DB / Memory">
            <DbMemoryTab {...studio.dbMemory} />
          </section>
          <section className="lens-panel" hidden={activeTab !== 'genre'} aria-label="Genre Converter">
            <GenreConverterTab />
          </section>
          <section className="lens-panel" hidden={activeTab !== 'mood'} aria-label="Mood Search">
            <MoodSearchTab />
          </section>
        </div>
      </main>
    </div>
  )
}
