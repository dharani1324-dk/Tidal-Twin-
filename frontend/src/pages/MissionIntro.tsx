/**
 * TidalTwin — Mission INTRO
 * =========================
 * The front door of the application. One continuous narrative that explains
 * what the system is, how it decides, what it is allowed to claim, and where
 * to go next — then hands over to the working surfaces.
 *
 * Design intent: cinematic and editorial rather than dashboard-dense. The
 * first viewport is a full-bleed opening; everything after it is a series of
 * measured sections that alternate between explanation and live data.
 *
 * Architectural constraints honoured here:
 *   - no polling; six requests on mount, three deferred behind scroll
 *   - every request fails independently, so one dead endpoint cannot blank
 *     the page
 *   - a failed or empty response renders a structured absence with a reason
 *   - no fabricated values anywhere, including the visuals
 *   - reduced-motion honoured for every reveal and the hero canvas
 *   - the only viewer-scale 3D surface in the app stays on /globe, so the
 *     intro costs no Cesium context and cannot fight the shell's renderer
 */
import Hero from '../components/mission/Hero'
import MissionNav from '../components/mission/MissionNav'
import { Problem, FourDTwin, Chain, Understand } from '../components/mission/Story'
import { TideSection, Provenance } from '../components/mission/Tide'
import { ObserveNext, Simulate, Replay } from '../components/mission/Actions'
import { Validation, LoopDiagram, Domains, Users, Finale } from '../components/mission/Proof'
import { useMissionCore } from '../components/mission/missionData'
import '../components/mission/mission.css'

export default function MissionIntro() {
  const core = useMissionCore()

  return (
    <div className="mission">
      <MissionNav />

      <main className="mission__main">
        <Hero core={core} />

        <Problem core={core} />
        <FourDTwin core={core} />
        <Chain />
        <Understand />

        <TideSection core={core} />
        <Provenance core={core} />

        <ObserveNext core={core} />
        <Simulate core={core} />
        <Replay />

        <Validation core={core} />
        <LoopDiagram />
        <Domains />
        <Users />
      </main>

      <Finale core={core} />
    </div>
  )
}
