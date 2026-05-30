# Mock Interview Assistant API

Production-oriented FastAPI backend for an AI mock interview mobile application. The API is deployed independently from the Android app and web frontend on Azure App Service.

The backend accepts job descriptions and CVs, extracts and retains their original text, produces structured AI analysis, generates personalized interview questions, transcribes recorded answers, evaluates interview responses, and tracks coaching trends across sessions.

## Architecture

```text
Android app / web frontend
            |
            v
Azure App Service (Linux)
FastAPI + Gunicorn + Uvicorn workers
            |
            +--> Supabase PostgreSQL
            |    Structured application data
            |
            +--> Supabase Storage
            |    Optional interview audio recordings
            |
            +--> OpenAI API
                 CV analysis, JD analysis, question generation,
                 Whisper transcription, and answer scoring
```

## Technology Stack

| Area | Technology |
| --- | --- |
| API framework | FastAPI |
| Production server | Gunicorn with Uvicorn workers |
| ORM | SQLAlchemy 2 |
| Production database | PostgreSQL hosted on Supabase |
| Object storage | Supabase Storage for optional audio persistence |
| AI integration | OpenAI Responses API and Whisper transcription |
| File parsing | `pypdf`, `python-docx`, and plain-text decoding |
| Configuration | `pydantic-settings` and Azure App Service settings |
| Deployment | Azure App Service on Linux |

## Repository Structure

This workspace contains the backend under `backend/`:

```text
backend/
|-- app/
|   |-- __init__.py
|   |-- main.py       # FastAPI routes, response mapping, and storage operations
|   |-- services.py   # OpenAI workflows, file extraction, and JSON normalization
|   |-- models.py     # SQLAlchemy database models
|   |-- schemas.py    # Pydantic request schemas
|   |-- database.py   # Database engine and session lifecycle
|   `-- config.py     # Environment-based application settings
`-- requirements.txt
```

The Azure deployment package should contain:

```text
backend/
requirements.txt
README.md
.gitignore
```

Do not deploy mobile, frontend, local data, log, or secret files:

```text
android/
frontend/
node_modules/
.env
backend/.env
backend/data/
*.log
.idea/
```

## Core Features

### CV and Job Description Processing

- Accepts pasted JD text or uploaded `.txt`, `.pdf`, and `.docx` files.
- Extracts content and stores the original text in PostgreSQL as `raw_text`.
- Returns `raw_text` from job, CV, and session responses so the mobile app can display the original document content.
- Generates structured AI analysis for reusable CV and JD library items.

### Personalized Interview Practice

- Creates interview sessions linked to a JD and an optional CV.
- Generates role-specific behavioral, technical, and scenario questions.
- Stores expected themes, STAR hints, difficulty, category, and relevance scores.
- Reuses generated questions when a session is reopened.

### Audio Transcription and Answer Evaluation

- Supports typed transcripts and recorded answers.
- Transcribes recorded answers with OpenAI Whisper.
- Scores answers with structured subscores, strengths, weaknesses, wording improvements, coaching tags, filler words, and a polished example answer.
- Uses answer duration as an evaluation signal when available.
- Stores recordings in Supabase Storage when storage credentials are configured.

### History and Coaching Trends

- Persists sessions, questions, responses, scores, transcripts, and recording references.
- Calculates average scores, subscore averages, and frequent coaching themes.
- Supports saving, reopening, and deleting interview sessions.

## Database Model

The API uses PostgreSQL through SQLAlchemy. Tables are created automatically when the service starts.

| Table | Purpose | Key fields |
| --- | --- | --- |
| `job_descriptions` | Saved JD library | `title`, `raw_text`, `analysis_json`, `created_at` |
| `resumes` | Saved CV library | `title`, `raw_text`, `analysis_json`, `created_at` |
| `interview_sessions` | Practice interview records | `job_id`, `resume_id`, `title`, `is_kept`, `created_at` |
| `questions` | Generated interview questions | `session_id`, `category`, `difficulty`, `question`, `expected_themes_json`, `star_hints_json`, `relevance_score` |
| `responses` | Candidate answers and evaluations | `transcript`, `audio_path`, `duration_seconds`, `evaluation_json`, `overall_score` |

JSON analysis and evaluation payloads are stored as text to preserve structured AI output while keeping the relational model simple.

## API Endpoints

FastAPI also exposes interactive OpenAPI documentation at `/docs` and `/redoc`.

### Health and Configuration

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Health check for deployment verification |
| `GET` | `/ai/status` | Reports configured AI clients and active model names without exposing credentials |

### Job Descriptions

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/jobs/analyze` | Analyze and save pasted JD text |
| `POST` | `/jobs/upload` | Extract, analyze, and save an uploaded JD |
| `GET` | `/jobs` | List saved JDs, including original `raw_text` |
| `DELETE` | `/jobs/{job_id}` | Delete a saved JD and its dependent sessions |
| `GET` | `/jobs/{job_id}/questions` | List questions generated for a JD |

### CVs

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/resumes/upload` | Extract, analyze, and save an uploaded CV |
| `GET` | `/resumes` | List saved CVs, including original `raw_text` |
| `DELETE` | `/resumes/{resume_id}` | Delete a CV and unlink it from existing sessions |

### Interview Sessions

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/sessions` | Create a practice session for a JD and optional CV |
| `PATCH` | `/sessions/{session_id}` | Mark a session as saved or unsaved |
| `DELETE` | `/sessions/{session_id}` | Delete a practice session |
| `POST` | `/questions/generate` | Generate personalized questions for a session |
| `GET` | `/history` | Return sessions, responses, and coaching trends |

### Responses and Recordings

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/responses/evaluate-text` | Evaluate a typed or previously transcribed response |
| `POST` | `/responses/evaluate-audio` | Upload, transcribe, store, and evaluate a recording |
| `POST` | `/responses/transcribe-audio` | Upload, store, and transcribe a recording before evaluation |
| `GET` | `/responses/{response_id}/audio` | Stream a stored recording |

## Environment Configuration

Production secrets are stored in:

```text
Azure Portal > App Service > Settings > Environment variables
```

They are injected into the application at runtime. Credentials must not be committed to GitHub or stored in the mobile application.

### Required Production Settings

```text
DATABASE_URL
OPENAI_LLM_API_KEY=your_openai_key
OPENAI_WHISPER_API_KEY=your_openai_key
CORS_ORIGINS
```

`SUPABASE_DATABASE_URL` can be used instead of `DATABASE_URL`. If neither database variable is configured, the API fails at startup rather than silently using a local database.

For a public production deployment, replace `CORS_ORIGINS=*` with the permitted frontend origins where possible.

### Optional Supabase Storage Settings

Configure these values to persist interview recordings outside the Azure App Service filesystem:

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
SUPABASE_STORAGE_BUCKET
DEFAULT_USER_ID
```

The Supabase service-role key is a backend-only secret. Never expose it in Android or frontend code.

If storage settings are omitted, recordings fall back to the local App Service filesystem. That is suitable for development only because App Service instances can be recycled.

### Optional AI Model Settings

```text
OPENAI_RESUME_MODEL=gpt-5-mini
OPENAI_JD_MODEL=gpt-5-mini
OPENAI_QUESTION_MODEL=gpt-5-mini
OPENAI_SCORING_MODEL=gpt-5
OPENAI_TRANSCRIBE_MODEL=whisper-1
OPENAI_TIMEOUT_SECONDS=180
```

The service uses local fallback responses if an OpenAI language-model request fails, allowing the application workflow to continue while surfacing a provider warning.

## Azure Deployment

Create an Azure App Service with:

```text
Operating system: Linux
Runtime stack: Python 3.11
```

Set the startup command in:

```text
Azure Portal > App Service > Settings > Configuration > Startup Command
```

Use:

```bash
cd backend && gunicorn -w 2 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:${PORT:-8000}
```

Azure installs the root `requirements.txt` during deployment. The root and backend requirements files are kept aligned for local and deployment workflows.

The Android app should call the Azure HTTPS URL:

```text
https://your-app-name.azurewebsites.net
```

Do not use these addresses in a released app:

```text
http://10.0.2.2:8000
http://localhost:8000
```

They are only valid for emulator or local development.

## Local Development

Create `backend/.env` for local-only configuration:

```text
DATABASE_URL=your_supabase_postgres_url
OPENAI_LLM_API_KEY=your_openai_key
OPENAI_WHISPER_API_KEY=your_openai_key
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Then install dependencies and start the API:

```powershell
pip install -r requirements.txt
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

Verify the service:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Expected response:

```json
{
  "status": "ok"
}
```

## Azure Deployment Verification

After deployment and restart:

```powershell
$base = "https://your-app-name.azurewebsites.net"

Invoke-RestMethod "$base/health"
Invoke-RestMethod "$base/ai/status" | ConvertTo-Json -Depth 10
Invoke-RestMethod "$base/jobs" | ConvertTo-Json -Depth 10
Invoke-RestMethod "$base/resumes" | ConvertTo-Json -Depth 10
```

Check that `/jobs` and `/resumes` include `raw_text`. This confirms that the deployed API version supports original CV and JD content in the mobile library detail view.

## Production Considerations

- Use PostgreSQL rather than SQLite for deployed environments.
- Store credentials in Azure App Service settings and rotate them when required.
- Persist recordings in Supabase Storage because local App Service files are not durable.
- Restrict CORS origins before exposing a browser frontend publicly.
- Review Azure and OpenAI usage limits before enabling audio workflows at scale.
- Expect cold starts on lower Azure App Service tiers after inactivity.
