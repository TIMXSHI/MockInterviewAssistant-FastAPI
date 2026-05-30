import json
import logging
from pathlib import Path
from typing import Any

from docx import Document
from openai import OpenAI
from pypdf import PdfReader

from app.config import get_settings

MAX_JOB_TEXT_CHARS = 14000
MAX_RESUME_TEXT_CHARS = 18000

JSON_ONLY_INSTRUCTIONS = (
    "Output valid JSON only. No Markdown/commentary. Use exactly requested keys; list fields are string arrays."
)

logger = logging.getLogger(__name__)


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def compact_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def json_array(value: str | None) -> list[Any]:
    loaded = json_loads(value, [])
    return loaded if isinstance(loaded, list) else []


def json_object(value: str | None) -> dict[str, Any]:
    loaded = json_loads(value, {})
    return loaded if isinstance(loaded, dict) else {}


def extract_text_from_upload(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    temp_path = Path("data") / f"upload-{Path(filename).name}"
    temp_path.parent.mkdir(exist_ok=True)
    temp_path.write_bytes(data)
    try:
        if suffix == ".pdf" or data.startswith(b"%PDF-"):
            reader = PdfReader(str(temp_path))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        elif suffix == ".docx" or data.startswith(b"PK"):
            doc = Document(str(temp_path))
            text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
        else:
            text = data.decode("utf-8", errors="ignore")
        return text.replace("\x00", "").strip()
    finally:
        temp_path.unlink(missing_ok=True)


def compact_text(value: str, limit: int) -> str:
    compacted = " ".join(value.split())
    return compacted[:limit] if limit > 0 else compacted


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [json.dumps(item, ensure_ascii=False) if isinstance(item, (dict, list)) else str(item) for item in value]
    if isinstance(value, dict):
        return [f"{key}: {item}" for key, item in value.items()]
    return [str(value)]


def stable_json_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def stable_string_list(value: Any) -> list[str]:
    return [item for item in (stable_json_string(item).strip() for item in string_list(value)) if item]


def relevance_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(score * 10, 1) if 0 <= score <= 1 else score


def normalize_analysis(value: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "summary": str(value.get("summary") or fallback["summary"]),
        "technical_skills": stable_string_list(value.get("technical_skills", fallback.get("technical_skills", []))),
        "soft_skills": stable_string_list(value.get("soft_skills", fallback.get("soft_skills", []))),
        "leadership_expectations": stable_string_list(value.get("leadership_expectations", fallback.get("leadership_expectations", []))),
        "domain_knowledge": stable_string_list(value.get("domain_knowledge", fallback.get("domain_knowledge", []))),
        "tools_platforms": stable_string_list(value.get("tools_platforms", fallback.get("tools_platforms", []))),
        "responsibilities": stable_string_list(value.get("responsibilities", fallback.get("responsibilities", []))),
        "focus_areas": stable_string_list(value.get("focus_areas", fallback.get("focus_areas", []))),
    }
    if value.get("provider_warning"):
        normalized["provider_warning"] = str(value["provider_warning"])
    return normalized


def normalize_resume_analysis(value: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "summary": str(value.get("summary") or fallback["summary"]),
        "experience_level": stable_json_string(value.get("experience_level") or fallback["experience_level"]),
        "technical_stack": stable_string_list(value.get("technical_stack", fallback.get("technical_stack", []))),
        "projects": stable_string_list(value.get("projects", fallback.get("projects", []))),
        "domain_experience": stable_string_list(value.get("domain_experience", fallback.get("domain_experience", []))),
        "leadership_examples": stable_string_list(value.get("leadership_examples", fallback.get("leadership_examples", []))),
        "potential_gaps": stable_string_list(value.get("potential_gaps", fallback.get("potential_gaps", []))),
    }
    if value.get("provider_warning"):
        normalized["provider_warning"] = str(value["provider_warning"])
    return normalized


def normalize_better_wording(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        value = [value] if value else []
    normalized = []
    for item in value:
        if isinstance(item, dict):
            normalized.append(
                {
                    "original": str(item.get("original", "")),
                    "better": str(item.get("better", "")),
                }
            )
        else:
            normalized.append({"original": "", "better": str(item)})
    return normalized


def normalize_evaluation(value: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    subscores = value.get("subscores", fallback.get("subscores", {}))
    if not isinstance(subscores, dict):
        subscores = fallback.get("subscores", {})
    numeric_subscores = {}
    for key, score in subscores.items():
        try:
            numeric_subscores[str(key)] = float(score)
        except (TypeError, ValueError):
            continue
    try:
        overall_score = float(value.get("overall_score", fallback["overall_score"]))
    except (TypeError, ValueError):
        overall_score = float(fallback["overall_score"])
    normalized = {
        "overall_score": overall_score,
        "subscores": numeric_subscores,
        "strengths": stable_string_list(value.get("strengths", fallback.get("strengths", []))),
        "weaknesses": stable_string_list(value.get("weaknesses", fallback.get("weaknesses", []))),
        "suggested_improvements": stable_string_list(value.get("suggested_improvements", fallback.get("suggested_improvements", []))),
        "better_wording": normalize_better_wording(value.get("better_wording", fallback.get("better_wording", []))),
        "improved_answer": str(value.get("improved_answer") or fallback["improved_answer"]),
        "coaching_tags": stable_string_list(value.get("coaching_tags", fallback.get("coaching_tags", []))),
        "filler_words": stable_string_list(value.get("filler_words", fallback.get("filler_words", []))),
    }
    if value.get("provider_warning"):
        normalized["provider_warning"] = str(value["provider_warning"])
    return normalized


class AiService:
    def __init__(self) -> None:
        self.settings = get_settings()
        llm_key = self.settings.openai_llm_api_key or self.settings.openai_whisper_api_key
        self.llm_client = OpenAI(api_key=llm_key, timeout=self.settings.openai_timeout_seconds) if llm_key else None
        whisper_key = self.settings.openai_whisper_api_key or self.settings.openai_llm_api_key
        self.transcription_client = OpenAI(api_key=whisper_key, timeout=self.settings.openai_timeout_seconds) if whisper_key else None

    def _json_response(self, model: str, system: str, user: str, fallback: dict[str, Any]) -> dict[str, Any]:
        if not self.llm_client:
            return fallback
        try:
            response = self.llm_client.responses.create(
                model=model,
                instructions=system,
                input=user,
                text={"format": {"type": "json_object"}},
            )
            content = getattr(response, "output_text", "") or "{}"
            return json.loads(content)
        except Exception as exc:
            logger.exception("OpenAI request failed for model %s; using local fallback", model)
            fallback["provider_warning"] = f"OpenAI request failed; using local fallback: {exc}"
            return fallback

    def analyze_job(self, title: str, text: str) -> dict[str, Any]:
        text = compact_text(text, MAX_JOB_TEXT_CHARS)
        fallback = {
            "summary": f"{title} role focused on delivery, stakeholder alignment, technical execution, and measurable outcomes.",
            "technical_skills": ["SQL", "Python", "data modeling", "APIs", "analytics platforms"],
            "soft_skills": ["communication", "stakeholder management", "problem solving", "leadership"],
            "leadership_expectations": ["own ambiguous problems", "influence cross-functional teams", "explain tradeoffs"],
            "domain_knowledge": ["data quality", "reporting workflows", "AI governance"],
            "tools_platforms": ["Power BI", "cloud services", "databases"],
            "responsibilities": ["deliver technical solutions", "translate business needs", "manage risks"],
            "focus_areas": ["STAR examples", "technical depth", "business impact", "executive communication"],
        }
        result = self._json_response(
            self.settings.jd_model,
            f"You are an expert interview coach. {JSON_ONLY_INSTRUCTIONS}",
            (
                "Task: analyze JD. Return json keys: summary(str), technical_skills[], soft_skills[], "
                "leadership_expectations[], domain_knowledge[], tools_platforms[], responsibilities[], "
                f"focus_areas[]. No nested objects.\nTitle:{compact_text(title, 0)}\nJD:{text}"
            ),
            fallback,
        )
        return normalize_analysis(result, fallback)

    def analyze_resume(self, title: str, text: str) -> dict[str, Any]:
        text = compact_text(text, MAX_RESUME_TEXT_CHARS)
        fallback = {
            "summary": f"{title} candidate profile with delivery experience, technical project work, and stakeholder-facing responsibilities.",
            "experience_level": "mid to senior",
            "technical_stack": ["SQL", "Python", "Power BI", "APIs", "AI tools"],
            "projects": ["analytics delivery", "automation", "reporting improvements"],
            "domain_experience": ["data", "technology delivery", "business analysis"],
            "leadership_examples": ["stakeholder alignment", "project coordination", "risk management"],
            "potential_gaps": ["prepare quantified examples", "connect technical choices to business outcomes"],
        }
        result = self._json_response(
            self.settings.resume_model,
            f"You are an experienced IT recruiter and hiring manager. {JSON_ONLY_INSTRUCTIONS}",
            (
                "Task: analyze resume. Return json keys: summary(str), experience_level(str), "
                "technical_stack[], projects[], domain_experience[], leadership_examples[], "
                f"potential_gaps[]. No nested objects.\nTitle:{compact_text(title, 0)}\nResume:{text}"
            ),
            fallback,
        )
        return normalize_resume_analysis(result, fallback)

    def generate_questions(self, analysis: dict[str, Any], resume_analysis: dict[str, Any] | None, count: int) -> list[dict[str, Any]]:
        fallback = [
            {
                "category": "Behavioral",
                "difficulty": "Medium",
                "question": "Tell me about a time you influenced stakeholders to support a technical recommendation relevant to this role.",
                "expected_themes": ["context", "stakeholders", "tradeoffs", "measurable outcome"],
                "star_hints": ["Set the business context", "Explain your action", "Quantify the result"],
                "relevance_score": 9.0,
            },
            {
                "category": "Technical",
                "difficulty": "Medium",
                "question": "How would you investigate a data quality issue in an executive dashboard?",
                "expected_themes": ["lineage", "validation", "root cause", "communication"],
                "star_hints": ["Describe the incident", "Show diagnostic steps", "Share prevention measures"],
                "relevance_score": 8.7,
            },
            {
                "category": "Scenario",
                "difficulty": "Hard",
                "question": "A production analytics pipeline fails before a board report is due. What do you do?",
                "expected_themes": ["triage", "stakeholder updates", "fallback plan", "postmortem"],
                "star_hints": ["Clarify urgency", "Prioritize mitigation", "Close with lessons learned"],
                "relevance_score": 8.9,
            },
        ]
        while len(fallback) < count:
            fallback.append({**fallback[len(fallback) % 3], "question": f"{fallback[len(fallback) % 3]['question']} #{len(fallback) + 1}"})

        result = self._json_response(
            self.settings.question_model,
            f"You are an experienced IT recruiter and hiring manager. {JSON_ONLY_INSTRUCTIONS}",
            (
                f"Task: create {count} personalized interview questions from JD+resume analysis. "
                "Mix Behavioral/Technical; cover stakeholder mgmt, conflict, delivery, technical decisions, "
                "and role SQL/Python/Power BI/AI only when supported. Return json "
                '{"questions":[{"category":"","difficulty":"","question":"","expected_themes":[],"star_hints":[],"relevance_score":0}]}. '
                f"No nested objects in arrays. JD={compact_json(analysis)} Resume={compact_json(resume_analysis or {})}"
            ),
            {"questions": fallback[:count]},
        )
        raw_questions = result.get("questions")
        if not isinstance(raw_questions, list) or not raw_questions:
            return fallback[:count]
        provider_warning = str(result.get("provider_warning") or "")
        normalized = []
        for item in raw_questions[:count]:
            if not isinstance(item, dict):
                continue
            question = {
                "category": str(item.get("category", "Behavioral")),
                "difficulty": str(item.get("difficulty", "Medium")),
                "question": str(item.get("question", "")),
                "expected_themes": stable_string_list(item.get("expected_themes", [])),
                "star_hints": stable_string_list(item.get("star_hints", [])),
                "relevance_score": relevance_score(item.get("relevance_score", 0)),
            }
            if provider_warning:
                question["provider_warning"] = provider_warning
            normalized.append(question)
        return normalized or fallback[:count]

    def transcribe(self, audio_path: Path) -> str:
        if not self.transcription_client:
            return "No OpenAI Whisper API key configured. Type or paste a transcript to evaluate a real answer."
        with audio_path.open("rb") as audio:
            result = self.transcription_client.audio.transcriptions.create(
                model=self.settings.openai_transcribe_model,
                file=audio,
            )
        return result.text

    def evaluate_answer(self, question: str, transcript: str, expected_themes: list[str], duration_seconds: float | None = None) -> dict[str, Any]:
        fallback = {
            "overall_score": 7.0,
            "subscores": {
                "technical_depth": 7,
                "communication": 7,
                "relevance": 7,
                "confidence": 6,
                "structure": 6,
            },
            "strengths": ["Addresses the question directly", "Uses professional language"],
            "weaknesses": ["Could quantify impact more clearly", "STAR structure could be sharper"],
            "suggested_improvements": ["Add measurable business outcomes", "Make the action and result more explicit"],
            "better_wording": ["I aligned the team around the tradeoff by linking the technical risk to customer impact."],
            "improved_answer": "A stronger answer would briefly set the context, explain the specific action taken, quantify the result, and close with what changed afterward.",
            "coaching_tags": ["needs stronger impact", "partial STAR structure"],
            "filler_words": [],
        }
        timing_context = ""
        if duration_seconds is not None:
            timing_context = (
                f" Duration:{round(duration_seconds, 1)} seconds. Judge timing for a spoken interview answer: "
                "under 45s may be too brief for complex behavioral/technical answers; 60-120s is usually strong; "
                "over 180s is likely too long unless the question is very complex. Reflect timing in weaknesses, "
                "suggested_improvements, and coaching_tags when relevant."
            )
        result = self._json_response(
            self.settings.scoring_model,
            f"You are a rigorous interview evaluator. {JSON_ONLY_INSTRUCTIONS}",
            (
                "Task: evaluate answer. Return json keys: overall_score(num), subscores{num}, strengths[], "
                "weaknesses[], suggested_improvements[], better_wording[{original,better}], improved_answer(str), "
                "coaching_tags[], filler_words[]. improved_answer must be a polished spoken interview answer "
                "in first person, written as 2-4 natural paragraphs, not bullets, not numbered steps, not headings. "
                "It should sound like what the candidate could say aloud, using clear STAR flow and concrete metrics where available. "
                f"{timing_context} Q:{compact_text(question, 0)} "
                f"Themes:{compact_json(expected_themes)} Transcript:{compact_text(transcript, 0)}"
            ),
            fallback,
        )
        return normalize_evaluation(result, fallback)


ai_service = AiService()
