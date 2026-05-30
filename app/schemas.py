from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AnalyzeJobRequest(BaseModel):
    title: str = "Imported role"
    text: str = Field(min_length=20)


class GenerateQuestionsRequest(BaseModel):
    job_id: int
    resume_id: int | None = None
    session_id: int | None = None
    count: int = Field(default=10, ge=3, le=25)


class CreateSessionRequest(BaseModel):
    job_id: int
    resume_id: int | None = None
    title: str | None = None


class UpdateSessionRequest(BaseModel):
    is_kept: bool


class EvaluateTextRequest(BaseModel):
    session_id: int
    question_id: int
    transcript: str = Field(min_length=5)
    duration_seconds: float | None = Field(default=None, ge=0)
    audio_path: str | None = None


class JobOut(BaseModel):
    id: int
    title: str
    analysis: dict[str, Any]
    created_at: datetime


class QuestionOut(BaseModel):
    id: int
    job_id: int
    category: str
    difficulty: str
    question: str
    expected_themes: list[str]
    star_hints: list[str]
    relevance_score: float


class SessionOut(BaseModel):
    id: int
    job_id: int
    title: str
    created_at: datetime


class ResponseOut(BaseModel):
    id: int
    session_id: int
    question_id: int
    transcript: str
    evaluation: dict[str, Any]
    overall_score: float
    created_at: datetime


class HistoryOut(BaseModel):
    sessions: list[dict[str, Any]]
    trends: dict[str, Any]
