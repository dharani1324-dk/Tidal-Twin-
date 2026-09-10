"""
OceanVerse AI - AI Assistant (Copilot) API
=========================================
Endpoints that power the chat copilot (multi-turn, context-aware ocean Q&A).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.ai.nlp.copilot import copilot_answer

router = APIRouter(prefix="/api/v1/assistant", tags=["AI Assistant"])


class QuestionInput(BaseModel):
    question: str
    context: dict = {}


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
    Ask the OceanVerse Copilot a natural-language question.
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


@router.get("/capabilities")
def capabilities() -> dict:
    """What the copilot can do — powers the UI affordance card."""
    return {
        "name": "OceanVerse Copilot",
        "capabilities": [
            {"key": "current", "label": "Live conditions", "desc": "Temperature, waves, salinity anywhere on the coast"},
            {"key": "safety", "label": "Safety advisory", "desc": "SAFE / CAUTION / DANGER + safest sailing window"},
            {"key": "events", "label": "Ocean events", "desc": "Marine heatwaves, flood risk, anomalies — live"},
            {"key": "risk", "label": "National risk", "desc": "Risk ranking of every monitored coast"},
            {"key": "validation", "label": "Model validation", "desc": "Is the model right? confidence, skill, deviation"},
            {"key": "forecast", "label": "Forecast", "desc": "Next 12 hours for any region"},
            {"key": "whatif", "label": "What-If scenarios", "desc": "'What if wind increases by 20%?'"},
            {"key": "storm", "label": "Cyclone watch", "desc": "Live storm track status"},
            {"key": "provenance", "label": "Provenance", "desc": "Where every number came from"},
        ],
        "examples": [
            "Is it safe to fish near Puri today?",
            "How confident are we in the model at Goa?",
            "Any marine heatwaves right now?",
            "Rank all coasts by risk today.",
            "What if wind increases by 30%?",
            "Where did the Mumbai temperature come from?",
        ],
    }