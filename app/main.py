from pathlib import Path
from uuid import uuid4
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request as UrlRequest, urlopen

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse, Response as StarletteResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import AUDIO_DIR, get_settings
from app.database import Base, engine, get_db
from app.models import InterviewSession, JobDescription, Question, Response, Resume
from app.schemas import AnalyzeJobRequest, CreateSessionRequest, EvaluateTextRequest, GenerateQuestionsRequest, UpdateSessionRequest
from app.services import ai_service, extract_text_from_upload, json_array, json_dumps, json_loads, json_object, stable_string_list

Base.metadata.create_all(bind=engine)


def ensure_database_schema() -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        question_columns = {row[1] for row in connection.execute(text("PRAGMA table_info(questions)"))}
        if "session_id" not in question_columns:
            connection.execute(text("ALTER TABLE questions ADD COLUMN session_id INTEGER"))
        if "api_log_json" not in question_columns:
            connection.execute(text("ALTER TABLE questions ADD COLUMN api_log_json TEXT"))

        session_columns = {row[1] for row in connection.execute(text("PRAGMA table_info(interview_sessions)"))}
        if "resume_id" not in session_columns:
            connection.execute(text("ALTER TABLE interview_sessions ADD COLUMN resume_id INTEGER"))
        if "is_kept" not in session_columns:
            connection.execute(text("ALTER TABLE interview_sessions ADD COLUMN is_kept BOOLEAN DEFAULT 0"))

        response_columns = {row[1] for row in connection.execute(text("PRAGMA table_info(responses)"))}
        if "duration_seconds" not in response_columns:
            connection.execute(text("ALTER TABLE responses ADD COLUMN duration_seconds FLOAT"))
        if "audio_path" not in response_columns:
            connection.execute(text("ALTER TABLE responses ADD COLUMN audio_path VARCHAR(500)"))


ensure_database_schema()

settings = get_settings()
app = FastAPI(title="AI Mock Interview Coach", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def supabase_storage_enabled() -> bool:
    return bool(settings.supabase_url and settings.supabase_service_role_key)


def supabase_storage_headers(content_type: str | None = None) -> dict[str, str]:
    if not settings.supabase_service_role_key:
        raise HTTPException(status_code=500, detail="Supabase service role key is not configured.")
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def supabase_object_url(object_path: str) -> str:
    if not settings.supabase_url:
        raise HTTPException(status_code=500, detail="Supabase URL is not configured.")
    encoded_path = quote(object_path, safe="/")
    return f"{settings.supabase_url.rstrip('/')}/storage/v1/object/{settings.supabase_storage_bucket}/{encoded_path}"


def upload_audio_object(object_path: str, data: bytes, content_type: str) -> None:
    request = UrlRequest(
        supabase_object_url(object_path),
        data=data,
        headers={
            **supabase_storage_headers(content_type),
            "x-upsert": "false",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:
            if response.status >= 400:
                raise HTTPException(status_code=502, detail="Supabase Storage upload failed.")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore") or exc.reason
        raise HTTPException(status_code=502, detail=f"Supabase Storage upload failed: {detail}") from exc
    except URLError as exc:
        raise HTTPException(status_code=502, detail=f"Supabase Storage upload failed: {exc.reason}") from exc


def download_audio_object(object_path: str) -> tuple[bytes, str]:
    request = UrlRequest(supabase_object_url(object_path), headers=supabase_storage_headers(), method="GET")
    try:
        with urlopen(request, timeout=60) as response:
            return response.read(), response.headers.get_content_type() or "audio/mp4"
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore") or exc.reason
        raise HTTPException(status_code=404, detail=f"Recording not found in Supabase Storage: {detail}") from exc
    except URLError as exc:
        raise HTTPException(status_code=502, detail=f"Supabase Storage download failed: {exc.reason}") from exc


def safe_storage_segment(value: str | int) -> str:
    segment = "".join(char if char.isalnum() or char in ("-", "_") else "-" for char in str(value).strip())
    return segment.strip("-") or "unknown"


async def persist_uploaded_audio(file: UploadFile, session_id: int, question_id: int) -> tuple[Path, str]:
    suffix = Path(file.filename or "answer.m4a").suffix or ".m4a"
    temp_path = AUDIO_DIR / f"{uuid4()}{suffix}"
    data = await file.read()
    temp_path.write_bytes(data)
    if not supabase_storage_enabled():
        return temp_path, str(temp_path)

    user_segment = safe_storage_segment(settings.default_user_id)
    object_path = f"users/{user_segment}/sessions/{session_id}/questions/{question_id}/{uuid4()}{suffix}"
    await run_in_threadpool(upload_audio_object, object_path, data, file.content_type or "audio/mp4")
    return temp_path, object_path


def question_out(question: Question) -> dict:
    return {
        "id": question.id,
        "job_id": question.job_id,
        "session_id": question.session_id,
        "category": question.category,
        "difficulty": question.difficulty,
        "question": question.question,
        "expected_themes": json_array(question.expected_themes_json),
        "star_hints": json_array(question.star_hints_json),
        "api_log": json_object(question.api_log_json) if question.api_log_json else None,
        "relevance_score": question.relevance_score,
    }


def resume_out(resume: Resume) -> dict:
    return {
        "id": resume.id,
        "title": resume.title,
        "raw_text": resume.raw_text,
        "analysis": json_loads(resume.analysis_json, {}),
        "created_at": resume.created_at,
    }


def response_out(response: Response) -> dict:
    return {
        "id": response.id,
        "session_id": response.session_id,
        "question_id": response.question_id,
        "question": question_out(response.question) if response.question else None,
        "transcript": response.transcript,
        "duration_seconds": response.duration_seconds,
        "audio_path": response.audio_path,
        "audio_url": f"/responses/{response.id}/audio" if response.audio_path else None,
        "evaluation": json_loads(response.evaluation_json, {}),
        "overall_score": response.overall_score,
        "created_at": response.created_at,
    }


def session_out(session: InterviewSession, responses: list[Response] | None = None) -> dict:
    response_rows = responses if responses is not None else session.responses
    question_rows = list(session.questions)
    if not question_rows:
        seen_question_ids: set[int] = set()
        for response in response_rows:
            if response.question and response.question.id not in seen_question_ids:
                question_rows.append(response.question)
                seen_question_ids.add(response.question.id)
    average = sum(response.overall_score for response in response_rows) / len(response_rows) if response_rows else 0
    return {
        "id": session.id,
        "job_id": session.job_id,
        "resume_id": session.resume_id,
        "title": session.title,
        "is_kept": session.is_kept,
        "created_at": session.created_at,
        "average_score": round(average, 1),
        "job": {
            "id": session.job.id,
            "title": session.job.title,
            "raw_text": session.job.raw_text,
            "analysis": json_loads(session.job.analysis_json, {}),
            "created_at": session.job.created_at,
        }
        if session.job
        else None,
        "resume": resume_out(session.resume) if session.resume else None,
        "questions": [question_out(question) for question in question_rows],
        "responses": [response_out(response) for response in response_rows],
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ai/status")
def ai_status() -> dict:
    return {
        "using_openai_client": ai_service.llm_client is not None,
        "using_llm_api_key": bool(settings.openai_llm_api_key or settings.openai_whisper_api_key),
        "using_whisper_api_key": ai_service.transcription_client is not None,
        "models": {
            "resume_parsing": settings.resume_model,
            "jd_analysis": settings.jd_model,
            "question_generation": settings.question_model,
            "voice_transcription": settings.openai_transcribe_model,
            "answer_scoring": settings.scoring_model,
        },
    }


@app.post("/jobs/analyze")
def analyze_job(payload: AnalyzeJobRequest, db: Session = Depends(get_db)) -> dict:
    analysis = ai_service.analyze_job(payload.title, payload.text)
    job = JobDescription(title=payload.title, raw_text=payload.text, analysis_json=json_dumps(analysis))
    db.add(job)
    db.commit()
    db.refresh(job)
    return {"id": job.id, "title": job.title, "raw_text": job.raw_text, "analysis": analysis, "created_at": job.created_at}


def extract_upload_or_400(file: UploadFile, data: bytes, default_name: str) -> str:
    try:
        return extract_text_from_upload(file.filename or default_name, data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read uploaded file: {exc}") from exc


@app.post("/jobs/upload")
async def upload_job(title: str = Form("Uploaded role"), file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    data = await file.read()
    text = extract_upload_or_400(file, data, "job.txt")
    if len(text) < 20:
        raise HTTPException(status_code=400, detail="Could not extract enough text from the uploaded file.")
    analysis = await run_in_threadpool(ai_service.analyze_job, title, text)
    job = JobDescription(title=title, raw_text=text, analysis_json=json_dumps(analysis))
    db.add(job)
    db.commit()
    db.refresh(job)
    return {"id": job.id, "title": job.title, "raw_text": job.raw_text, "analysis": analysis, "created_at": job.created_at}


@app.post("/resumes/upload")
async def upload_resume(title: str = Form("Uploaded resume"), file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    data = await file.read()
    text_value = extract_upload_or_400(file, data, "resume.txt")
    if len(text_value) < 20:
        raise HTTPException(status_code=400, detail="Could not extract enough text from the uploaded resume.")
    uploaded_name = Path(file.filename or "").name
    effective_title = uploaded_name if title.strip() in ("", "Uploaded resume", "Candidate resume") else title.strip()
    effective_title = (effective_title or "Uploaded resume")[:255]
    analysis = await run_in_threadpool(ai_service.analyze_resume, effective_title, text_value)
    resume = Resume(title=effective_title, raw_text=text_value, analysis_json=json_dumps(analysis))
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume_out(resume)


@app.get("/jobs")
def list_jobs(db: Session = Depends(get_db)) -> list[dict]:
    jobs = db.query(JobDescription).order_by(JobDescription.created_at.desc()).all()
    return [{"id": job.id, "title": job.title, "raw_text": job.raw_text, "analysis": json_loads(job.analysis_json, {}), "created_at": job.created_at} for job in jobs]


@app.get("/resumes")
def list_resumes(db: Session = Depends(get_db)) -> list[dict]:
    resumes = db.query(Resume).order_by(Resume.created_at.desc()).all()
    return [resume_out(resume) for resume in resumes]


@app.delete("/jobs/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db)) -> dict:
    job = db.get(JobDescription, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    db.delete(job)
    db.commit()
    return {"deleted": True, "id": job_id}


@app.delete("/resumes/{resume_id}")
def delete_resume(resume_id: int, db: Session = Depends(get_db)) -> dict:
    resume = db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    db.query(InterviewSession).filter(InterviewSession.resume_id == resume_id).update({"resume_id": None})
    db.delete(resume)
    db.commit()
    return {"deleted": True, "id": resume_id}


@app.post("/questions/generate")
def generate_questions(payload: GenerateQuestionsRequest, db: Session = Depends(get_db)) -> list[dict]:
    job = db.get(JobDescription, payload.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    resume = db.get(Resume, payload.resume_id) if payload.resume_id else None
    session = db.get(InterviewSession, payload.session_id) if payload.session_id else None
    if payload.resume_id and not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    if payload.session_id and not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session and session.questions:
        return [question_out(question) for question in session.questions]
    generated = ai_service.generate_questions(json_object(job.analysis_json), json_object(resume.analysis_json) if resume else None, payload.count)
    questions: list[Question] = []
    for item in generated:
        question = Question(
            job_id=job.id,
            session_id=session.id if session else None,
            category=item.get("category", "Behavioral"),
            difficulty=item.get("difficulty", "Medium"),
            question=item.get("question", ""),
            expected_themes_json=json_dumps(stable_string_list(item.get("expected_themes", []))),
            star_hints_json=json_dumps(stable_string_list(item.get("star_hints", []))),
            api_log_json=json_dumps(item),
            relevance_score=float(item.get("relevance_score", 0)),
        )
        db.add(question)
        questions.append(question)
    db.commit()
    for question in questions:
        db.refresh(question)
    return [question_out(question) for question in questions]


@app.get("/jobs/{job_id}/questions")
def list_questions(job_id: int, db: Session = Depends(get_db)) -> list[dict]:
    questions = db.query(Question).filter(Question.job_id == job_id).order_by(Question.id.asc()).all()
    return [question_out(question) for question in questions]


@app.post("/sessions")
def create_session(payload: CreateSessionRequest, db: Session = Depends(get_db)) -> dict:
    job = db.get(JobDescription, payload.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    resume = db.get(Resume, payload.resume_id) if payload.resume_id else None
    if payload.resume_id and not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    session = InterviewSession(job_id=job.id, resume_id=resume.id if resume else None, title=payload.title or f"Interview for {job.title}")
    db.add(session)
    db.commit()
    db.refresh(session)
    return session_out(session)


@app.patch("/sessions/{session_id}")
def update_session(session_id: int, payload: UpdateSessionRequest, db: Session = Depends(get_db)) -> dict:
    session = db.get(InterviewSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.is_kept = payload.is_kept
    db.commit()
    db.refresh(session)
    return session_out(session)


@app.delete("/sessions/{session_id}")
def delete_session(session_id: int, db: Session = Depends(get_db)) -> dict:
    session = db.get(InterviewSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    db.delete(session)
    db.commit()
    return {"deleted": True, "id": session_id}


@app.post("/responses/evaluate-text")
def evaluate_text(payload: EvaluateTextRequest, db: Session = Depends(get_db)) -> dict:
    session = db.get(InterviewSession, payload.session_id)
    question = db.get(Question, payload.question_id)
    if not session or not question:
        raise HTTPException(status_code=404, detail="Session or question not found")
    evaluation = ai_service.evaluate_answer(question.question, payload.transcript, json_array(question.expected_themes_json), payload.duration_seconds)
    response = Response(
        session_id=session.id,
        question_id=question.id,
        transcript=payload.transcript,
        duration_seconds=payload.duration_seconds,
        audio_path=payload.audio_path,
        evaluation_json=json_dumps(evaluation),
        overall_score=float(evaluation.get("overall_score", 0)),
    )
    db.add(response)
    db.commit()
    db.refresh(response)
    return response_out(response)


def ranged_audio_response(data: bytes, content_type: str, range_header: str | None) -> StarletteResponse:
    headers = {"Accept-Ranges": "bytes"}
    if not range_header:
        return StarletteResponse(data, media_type=content_type, headers=headers)
    try:
        unit, requested_range = range_header.split("=", 1)
        if unit.lower() != "bytes" or "," in requested_range:
            raise ValueError
        start_text, end_text = requested_range.split("-", 1)
        if start_text:
            start = int(start_text)
            end = int(end_text) if end_text else len(data) - 1
        else:
            suffix_length = int(end_text)
            start = max(0, len(data) - suffix_length)
            end = len(data) - 1
        if start < 0 or end < start or start >= len(data):
            raise ValueError
        end = min(end, len(data) - 1)
    except ValueError as exc:
        raise HTTPException(
            status_code=416,
            detail="Requested audio range is not satisfiable.",
            headers={"Content-Range": f"bytes */{len(data)}"},
        ) from exc
    headers["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
    return StarletteResponse(data[start : end + 1], status_code=206, media_type=content_type, headers=headers)


@app.get("/responses/{response_id}/audio")
def response_audio(response_id: int, request: Request, db: Session = Depends(get_db)) -> StarletteResponse:
    response = db.get(Response, response_id)
    if not response or not response.audio_path:
        raise HTTPException(status_code=404, detail="Recording not found")
    if supabase_storage_enabled() and not Path(response.audio_path).is_absolute():
        data, content_type = download_audio_object(response.audio_path)
        return ranged_audio_response(data, content_type, request.headers.get("range"))
    audio_path = Path(response.audio_path)
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Recording file not found")
    return FileResponse(audio_path, media_type="audio/mp4", filename=audio_path.name)


@app.post("/responses/evaluate-audio")
async def evaluate_audio(
    session_id: int = Form(...),
    question_id: int = Form(...),
    file: UploadFile = File(...),
    duration_seconds: float | None = Form(None),
    db: Session = Depends(get_db),
) -> dict:
    session = db.get(InterviewSession, session_id)
    question = db.get(Question, question_id)
    if not session or not question:
        raise HTTPException(status_code=404, detail="Session or question not found")
    temp_path, stored_audio_path = await persist_uploaded_audio(file, session.id, question.id)
    try:
        transcript = await run_in_threadpool(ai_service.transcribe, temp_path)
    finally:
        if supabase_storage_enabled():
            temp_path.unlink(missing_ok=True)
    evaluation = await run_in_threadpool(ai_service.evaluate_answer, question.question, transcript, json_array(question.expected_themes_json), duration_seconds)
    response = Response(
        session_id=session.id,
        question_id=question.id,
        transcript=transcript,
        audio_path=stored_audio_path,
        duration_seconds=duration_seconds,
        evaluation_json=json_dumps(evaluation),
        overall_score=float(evaluation.get("overall_score", 0)),
    )
    db.add(response)
    db.commit()
    db.refresh(response)
    return response_out(response)


@app.post("/responses/transcribe-audio")
async def transcribe_audio(
    session_id: int = Form(...),
    question_id: int = Form(...),
    file: UploadFile = File(...),
    duration_seconds: float | None = Form(None),
    db: Session = Depends(get_db),
) -> dict:
    session = db.get(InterviewSession, session_id)
    question = db.get(Question, question_id)
    if not session or not question:
        raise HTTPException(status_code=404, detail="Session or question not found")
    temp_path, stored_audio_path = await persist_uploaded_audio(file, session.id, question.id)
    try:
        transcript = await run_in_threadpool(ai_service.transcribe, temp_path)
    finally:
        if supabase_storage_enabled():
            temp_path.unlink(missing_ok=True)
    return {"session_id": session.id, "question_id": question.id, "transcript": transcript, "audio_path": stored_audio_path, "duration_seconds": duration_seconds}


@app.get("/history")
def history(db: Session = Depends(get_db)) -> dict:
    sessions = db.query(InterviewSession).order_by(InterviewSession.created_at.desc()).all()
    session_rows = []
    all_responses: list[Response] = []
    for session in sessions:
        responses = db.query(Response).filter(Response.session_id == session.id).order_by(Response.created_at.asc()).all()
        all_responses.extend(responses)
        session_rows.append(session_out(session, responses))

    subscores: dict[str, list[float]] = {}
    tags: dict[str, int] = {}
    for response in all_responses:
        evaluation = json_object(response.evaluation_json)
        for key, value in evaluation.get("subscores", {}).items():
            subscores.setdefault(key, []).append(float(value))
        for tag in evaluation.get("coaching_tags", []):
            tags[tag] = tags.get(tag, 0) + 1

    trends = {
        "average_overall": round(sum(r.overall_score for r in all_responses) / len(all_responses), 1) if all_responses else 0,
        "subscore_averages": {key: round(sum(values) / len(values), 1) for key, values in subscores.items()},
        "frequent_weak_areas": sorted(tags.items(), key=lambda item: item[1], reverse=True)[:5],
    }
    return {"sessions": session_rows, "trends": trends}
