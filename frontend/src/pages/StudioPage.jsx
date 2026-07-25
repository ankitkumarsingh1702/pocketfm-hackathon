import { TABS } from '../config/constants'
import { useStudio } from '../controllers/useStudio'
import StudioHeader from '../components/StudioHeader'
import StoryInput from '../components/StoryInput'
import SuperpowersStrip from '../components/SuperpowersStrip'
import { Tabs } from '../components/primitives'
import AudienceSimulatorTab from '../components/tabs/AudienceSimulatorTab'
import CliffhangerOptimizerTab from '../components/tabs/CliffhangerOptimizerTab'
import DbMemoryTab from '../components/tabs/DbMemoryTab'
import StoryCanonTab from '../components/tabs/StoryCanonTab'
import WritersRoom from '../WritersRoom'

/**
 * Simulated Studio page — pure composition.
 *
 * All state, data fetching, and orchestration live in `useStudio`; this
 * component only maps that state onto presentational components and forwards
 * callbacks. No business logic here by design.
 */
export default function StudioPage() {
  const studio = useStudio()
  const { activeTab, setActiveTab, story, setStory, run, isLoading, canRun } = studio

  // Fluid full-bleed shell — content spans the viewport, with responsive side
  // padding so it never sits flush against the screen edges.
  const shell = { width: '100%', boxSizing: 'border-box' }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--canvas)', display: 'flex', flexDirection: 'column' }}>
      <StudioHeader health={studio.health} />

      <div style={{ ...shell, padding: '10px clamp(20px,4vw,56px) 0' }}>
        <div className="label-upper" style={{ fontSize: 11, marginBottom: 12 }}>
          P5 · Creator Superpowers
        </div>
        <SuperpowersStrip />
      </div>

      <main style={{ ...shell, padding: '28px clamp(20px,4vw,56px) 80px' }}>
        {/* The Writers Room and Story Canon tabs have their own composers, so
            the shared story input is only shown for the other lenses. */}
        {activeTab !== 'room' && activeTab !== 'canon' && activeTab !== 'db' && (
          <StoryInput
            value={story}
            onChange={setStory}
            onRun={run}
            loading={isLoading}
            canRun={canRun}
          />
        )}

        <div style={{ marginTop: 40 }}>
          <Tabs tabs={TABS} active={activeTab} onChange={setActiveTab} />
        </div>

        {activeTab === 'sim' && <AudienceSimulatorTab {...studio.audience} />}
        {activeTab === 'opt' && <CliffhangerOptimizerTab {...studio.cliffhanger} />}
        {activeTab === 'room' && <WritersRoom />}
        {activeTab === 'canon' && <StoryCanonTab {...studio.canon} />}
        {activeTab === 'db' && <DbMemoryTab {...studio.dbMemory} />}
      </main>
    </div>
  )
}
