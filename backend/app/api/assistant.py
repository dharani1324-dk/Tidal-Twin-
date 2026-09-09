"""
OceanVerse AI - AI Assistant API
================================
Endpoints that power the chat assistant (natural language ocean queries).
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.ai.nlp.assistant import answer_question

router = APIRouter(prefix="/api/v1/assistant", tags=["AI Assistant"])


class QuestionInput(BaseModel):
    question: str


class AnswerOutput(BaseModel):
    question: str
    answer: str
    intent: str
    timestamp: str


@router.post("/ask", response_model=AnswerOutput)
def ask(question_input: QuestionInput, db: Session = Depends(get_db)):
    """
    Ask the Ocean AI Assistant a natural-language question.
    It parses the intent, queries real ocean data, and replies in English.
    """
    from datetime import datetime, timezone

    result = answer_question(db, question_input.question)

    return AnswerOutput(
        question=question_input.question,
        answer=result["answer"],
        intent=result["intent"],
        timestamp=datetime.now(timezone.utc).isoformat(),
    )