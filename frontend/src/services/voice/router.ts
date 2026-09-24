/**
 * TIDE Voice Agent - question category router (pure, dependency-free).
 *
 * Used by the TEXT FALLBACK path (when the realtime engine or the microphone
 * is unavailable) to pick the right existing endpoint or explanation, and as
 * a self-documenting mirror of the backend routing rules (see
 * app/modules/voice/agent.py::build_instructions).
 */

export type VoiceCategory = 'A' | 'B' | 'C' | 'D' | 'E' | 'F'

export const CATEGORY_LABELS: Record<VoiceCategory, string> = {
  A: 'project/identity',
  B: 'tide twin data',
  C: 'TIDE decision intelligence',
  D: 'current outside-world',
  E: 'general knowledge',
  F: 'UI control / navigation',
}

const CONTROL_OPENERS =
  /^(go to|take me to|show me the|show me|open the|open|navigate to|navigate|move to|fly to|zoom to|zoom into|zoom|drill down|drill into|switch to|set depth|depth to|turn on|turn off|hide the|hide|reveal the|reveal|scroll to|jump to|jump|next candidate)/

const CONTROL_INSIDE =
  /\b(layers?|panels?|drill down|drill into|toggle the|toggle|switch on|switch off|on the globe|in 3d|3d view)\b/

const SHORT_COMMANDS = /^(next|previous|prev|back|home|globe|forensics|tide|replay|validation|scenarios?|monitoring|assistant|safety|risk|reports|stories)$/

const PROJECT_IDENTITY =
  /\b(what is tidal ?twin|what can you do|who are you|who built|who made|about this (platform|project|system)|what does (this|tidal ?twin) do|version|release name|capabilities of this platform)\b/i

const CURRENT_EXTERNAL =
  /\b(news|headlines?|today'?s? (news|events)|latest news|current cyclone|hurricane (now|today)|what happened (today|this week)|live updates|stock prices?|currency|election|sports|current affairs|world (today|news))\b/i

const TIDE_DECISION =
  /\b(recommend|tide|sample next|next (observation|sample)|observe next|deploy (a|an|the)|sensor|should we|trust|confidence|confident|verdict|evidence|uncertain|uncertainty|data gap|disagreement|validat(e|ion|ed)|benchmark|why (there|this location)|what if|counterfactual|scenario|simulate)\b/i

const DATA_REQUEST =
  /\b(temperature|salinity|oxygen|chlorophyll|wave|waves|current|currents|pressure|density|ph|nutrients|observation|observations|reading|readings|data|values?|measurements?|anomal(y|ies)|event|events|heatwave|forecast|trend|depth profile|argo|float|satellite|sst|ersst|viirs|glider|sources?|provenance|real or (simulated|fake)|demonstration|model vs|disagree)\b/i

const CURRENT_CONTEXT =
  /\b(here|here now|this (coast|region|location|area|zone|place|site|box)|right now|what'?s? happening (here|now)|currently|on screen|this view|focused)\b/i

const GENERAL_KNOWLEDGE =
  /\b(what is a |what are |explain|mean(ing)? of|define|why do|why does|how do|how does|definition|concept of|thermoclin|phytoplankton|chlorophyll a (is|means)|monsoon|upwelling|el ni|la ni|principal component|isotherm|salinity (is|means)|sea level rise|coastal erosion|erosion)\b/i

const QUESTION_MARK = /\?/

export interface RouteDecision {
  category: VoiceCategory
  reasons: string[]
}

/** Classify a question into the six documented categories (A-F). */
export function classifyCategory(question: string, page = ''): RouteDecision {
  const q = (question || '').trim()
  const reasons: string[] = []
  const lower = q.toLowerCase()

  // F - explicit UI control / navigation.
  if (CONTROL_OPENERS.test(lower) || CONTROL_INSIDE.test(lower) || SHORT_COMMANDS.test(lower)) {
    reasons.push('navigation or control verbs')
    return { category: 'F', reasons }
  }

  // A - project identity.
  if (PROJECT_IDENTITY.test(q)) {
    reasons.push('asks about TidalTwin itself')
    return { category: 'A', reasons }
  }

  // D - current outside-world information.
  if (CURRENT_EXTERNAL.test(q)) {
    reasons.push('references news/live outside-world info')
    return { category: 'D', reasons }
  }

  // C - TIDE / decision intelligence.
  if (TIDE_DECISION.test(q)) {
    reasons.push('recommendation, confidence, validation or what-if wording')
    return { category: 'C', reasons }
  }

  // B - platform data question (or current-context reference).
  if (DATA_REQUEST.test(q)) {
    reasons.push('mentions an ocean variable, dataset, event or anomaly')
    return { category: 'B', reasons }
  }
  if (CURRENT_CONTEXT.test(q)) {
    reasons.push('references the current on-screen context')
    return { category: 'B', reasons }
  }

  // E - general knowledge / concept explanation.
  if (GENERAL_KNOWLEDGE.test(q)) {
    reasons.push('general ocean-science concept wording')
    return { category: 'E', reasons }
  }

  // Heuristic: a bare question about something happening on a known page.
  if (QUESTION_MARK.test(q) && page === 'tide') {
    reasons.push('question asked from the TIDE page')
    return { category: 'C', reasons }
  }

  // Default: platform data (the model should resolve context first).
  reasons.push('default to platform data with context resolution')
  return { category: 'B', reasons }
}

/** Short, human feedback line for the transcript/telemetry. */
export function routeFeedback(decision: RouteDecision): string {
  return `Category ${decision.category} - ${CATEGORY_LABELS[decision.category]} (${decision.reasons.join('; ')})`
}