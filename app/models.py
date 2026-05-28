from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class JobDescription(Base):
    __tablename__ = "job_descriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), default="Imported role")
    raw_text: Mapped[str] = mapped_column(Text)
    analysis_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    questions: Mapped[list["Question"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    sessions: Mapped[list["InterviewSession"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), default="Uploaded resume")
    raw_text: Mapped[str] = mapped_column(Text)
    analysis_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    sessions: Mapped[list["InterviewSession"]] = relationship(back_populates="resume")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_descriptions.id"))
    session_id: Mapped[int | None] = mapped_column(ForeignKey("interview_sessions.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(80))
    difficulty: Mapped[str] = mapped_column(String(40))
    question: Mapped[str] = mapped_column(Text)
    expected_themes_json: Mapped[str] = mapped_column(Text)
    star_hints_json: Mapped[str] = mapped_column(Text)
    api_log_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    relevance_score: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job: Mapped[JobDescription] = relationship(back_populates="questions")
    session: Mapped["InterviewSession | None"] = relationship(back_populates="questions")
    responses: Mapped[list["Response"]] = relationship(back_populates="question", cascade="all, delete-orphan")


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_descriptions.id"))
    resume_id: Mapped[int | None] = mapped_column(ForeignKey("resumes.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    is_kept: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job: Mapped[JobDescription] = relationship(back_populates="sessions")
    resume: Mapped[Resume | None] = relationship(back_populates="sessions")
    questions: Mapped[list["Question"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    responses: Mapped[list["Response"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class Response(Base):
    __tablename__ = "responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_sessions.id"))
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    transcript: Mapped[str] = mapped_column(Text)
    audio_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    evaluation_json: Mapped[str] = mapped_column(Text)
    overall_score: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped[InterviewSession] = relationship(back_populates="responses")
    question: Mapped[Question] = relationship(back_populates="responses")
