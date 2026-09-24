"""
TidalTwin - AI Assistant (Copilot) API
=========================================
Endpoints that power the chat copilot (multi-turn, context-aware ocean Q&A).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.ai.nlp.copilot import copilot_answer
from app.modules.ai.nlp.multimodal import multimodal_fuse, now_iso as multimodal_now

router = APIRouter(prefix="/api/v1/assistant", tags=["AI Assistant"])


class QuestionInput(BaseModel):
    question: str
    context: dict = {}


class MultiModalInput(BaseModel):
    text: str
    media: dict | None = None


class AnswerOutput(BaseModel):
    question: str
    answer: str
    intent: str
    location: str | None = None
    location_id: int | None = None
    data: dict | None = None
    suggestions: list[str] = []
    sources: list[str] = []
    steps: list[str] = []
    context: dict = {}
    timestamp: str


@router.post("/ask", response_model=AnswerOutput)
def ask(question_input: QuestionInput, db: Session = Depends(get_db)):
    """
    Ask the TidalTwin Copilot a natural-language question.
    Pass `context` (last_location_id / last_intent) for multi-turn follow-ups.
    """
    result = copilot_answer(db, question_input.question, question_input.context)

    return AnswerOutput(
        question=question_input.question,
        answer=result["answer"],
        intent=result["intent"],
        location=result.get("location"),
        location_id=result.get("location_id"),
        data=result.get("data"),
        suggestions=result.get("suggestions", []),
        sources=result.get("sources", []),
        steps=result.get("steps", []),
        context=result.get("context", {}),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.post("/multimodal", response_model=AnswerOutput)
def multimodal(input: MultiModalInput, db: Session = Depends(get_db)):
    """
    Fuse a pasted document/news/report/satellite-metadata + live ocean
    sensors into one evidence-based answer (Multimodal Ocean AI).
    """
    result = multimodal_fuse(db, input.text, input.media)

    return AnswerOutput(
        question=input.text[:120] or "(document input)",
        answer=result["answer"],
        intent=result["intent"],
        location=result.get("location"),
        location_id=result.get("location_id"),
        data=result.get("data"),
        suggestions=result.get("suggestions", []),
        sources=result.get("sources", []),
        steps=result.get("steps", []),
        context=result.get("context", {}),
        timestamp=multimodal_now(),
    )


@router.get("/capabilities")
def capabilities() -> dict:
    """What the copilot can do — powers the UI affordance card."""
    return {
        "name": "TidalTwin Copilot",
        "capabilities": [
            {"key": "current", "label": "Live conditions", "desc": "Temperature, waves, salinity anywhere on the coast", "ask": "What are the live sea conditions near Mumbai?"},
            {"key": "safety", "label": "Safety advisory", "desc": "SAFE / CAUTION / DANGER + safest sailing window", "ask": "Is it safe to fish near Goa today?"},
            {"key": "events", "label": "Ocean events", "desc": "Marine heatwaves, flood risk, anomalies — live", "ask": "Are there any marine heatwaves or ocean events right now?"},
            {"key": "risk", "label": "National risk", "desc": "Risk ranking of every monitored coast", "ask": "Rank all monitored coasts by risk today."},
            {"key": "validation", "label": "Model validation", "desc": "Is the model right? confidence, skill, deviation", "ask": "How confident is the model at Goa versus the observations?"},
            {"key": "forecast", "label": "Forecast", "desc": "Next 12 hours for any region", "ask": "What is the forecast for the next 12 hours at Goa?"},
            {"key": "whatif", "label": "What-If scenarios", "desc": "'What if wind increases by 20%?'", "ask": "What would happen if wind increases by 30% at Goa?"},
            {"key": "storm", "label": "Cyclone watch", "desc": "Live storm track status", "ask": "Where is the cyclone heading and when does it make landfall?"},
            {"key": "provenance", "label": "Provenance", "desc": "Where every number came from", "ask": "Where did the sea temperature reading at Mumbai come from?"},
            {"key": "carbon", "label": "Carbon flux", "desc": "Air-sea CO₂ flux, sinks, blue-carbon potential", "ask": "Which coast is the strongest CO₂ sink?"},
            {"key": "lights", "label": "Light pollution", "desc": "ALAN exposure + biota impact per coast", "ask": "How is artificial light pollution affecting marine life near Mumbai?"},
            {"key": "sensing", "label": "Satellite fusion", "desc": "Remote-sensing harmonization & confidence", "ask": "Show the remote-sensing fusion confidence across the coasts."},
            {"key": "recommend", "label": "Observation planner", "desc": "Where to sample next, and why", "ask": "Where should we sample next and why?"},
            {"key": "tide", "label": "TIDE recommendation", "desc": "Explainable observation ranking via TIDE-Loop", "ask": "What evidence supports the TIDE recommendation for Mumbai?"},
            {"key": "adaptive", "label": "Adaptive detection", "desc": "Self-calibrating anomaly thresholds", "ask": "What do the adaptive anomaly thresholds say right now?"},
            {"key": "multimodal", "label": "Multimodal fusion", "desc": "Paste a report/news/NETCDF summary — I'll verify it against live sensors", "ask": "Cross-check a field report against live sensors."},
            {"key": "fisheries", "label": "Fisheries advisory", "desc": "Fish-aggregation zones, target species, seasonal calendar", "ask": "Where are the fish aggregation zones today?"},
            {"key": "coral", "label": "Coral stress", "desc": "NOAA-style DHW bleaching index per reef", "ask": "What is the coral bleaching risk for the Gulf of Mannar reef?"},
            {"key": "spill", "label": "Spill & SAR", "desc": "Oil-slick or missing-person drift prediction", "ask": "Where would an oil spill near Mumbai drift over 24 hours?"},
            {"key": "slr", "label": "Sea-level rise", "desc": "Inundation footprint for any +m scenario", "ask": "Which coastal towns are flooded under 1 metre of sea-level rise?"},
            {"key": "beach", "label": "Beach safety", "desc": "Rip-current flags and lifeguard actions", "ask": "Which beach has the strongest rip currents today?"},
            {"key": "impact", "label": "Economic impact", "desc": "₹ loss estimates by sector for active events", "ask": "What is the estimated economic impact of current ocean events?"},
            {"key": "brief", "label": "Intelligence brief", "desc": "One fused brief — ANSWER / EVIDENCE / CONFIDENCE / LIMITATIONS / NEXT ACTION across twin, validation, forensics and TIDE", "ask": "Give me the ocean intelligence brief."},
            {"key": "tide_validation", "label": "TIDE validation & benchmarks", "desc": "Honest validation status, baseline benchmarks and limitations — TIDE is tested, not scientifically validated", "ask": "Is TIDE scientifically validated?"},
        ],
        "examples": [
            "Is it safe to fish near Puri today?",
            "How confident are we in the model at Goa?",
            "Any marine heatwaves right now?",
            "Rank all coasts by risk today.",
            "What if wind increases by 30%?",
            "Where did the Mumbai temperature come from?",
            "Which coast is the strongest CO2 sink?",
            "Where should we sample next?",
            "What evidence supports the TIDE recommendation for Mumbai?",
            "Cross-check this report: 'SST at Mumbai reached 30.2°C this week with high chlorophyll.'",
            "Where is the best fishing zone today?",
            "What is the economic impact of the active events?",
            "Is it safe to swim at Goa right now?",
            "Give me the ocean intelligence brief.",
            "What gets inundated at +1m sea-level rise?",
        ],
    }