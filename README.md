# Mock Interview Assistant API

Backend API host for the Mock Interview Assistant mobile application using FastAPI and Azure Web App.

This deployment hosts only the backend API service. The Android app and frontend UI are deployed separately and communicate directly with the Azure-hosted API.

---

# Azure Runtime

Create an Azure Web App using:

```text
Operating system: Linux
Runtime stack: Python 3.11
```

The FastAPI application entry point is:

```text
app/main.py
```

The mobile app connects directly to:

```text
https://your-app-name.azurewebsites.net
```

---

# GitHub Repository Structure

```text
.github/
app/
requirements.txt
README.md
.gitignore
```

Application structure:

```text
app/
├── __init__.py
├── main.py
├── services.py
├── models.py
├── schemas.py
├── database.py
└── config.py
```

---

# Azure Startup Command

In Azure Portal:

```text
Web App > Configuration > General settings > Startup Command
```

Set:

```bash
gunicorn -w 2 -k uvicorn.workers.UvicornWorker app.main:app
```

---

# Azure Application Settings

Configure the following in:

```text
Azure Portal > Web App > Configuration > Application settings
```

Required settings:

```text
DATABASE_URL=postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres?sslmode=require
OPENAI_LLM_API_KEY=your_openai_key
OPENAI_WHISPER_API_KEY=your_openai_key
CORS_ORIGINS=*
```

Optional:

```text
SUPABASE_DATABASE_URL=your_supabase_connection
```

Do not commit API keys, database credentials, or `.env` files to GitHub.

---

# Required Python Packages

Example `requirements.txt`:

```text
fastapi
uvicorn
gunicorn
sqlalchemy
psycopg[binary]
python-multipart
openai
pydantic
pydantic-settings
python-docx
pypdf
```

---

# API Endpoints

Examples:

```text
GET    /health
GET    /ai/status
GET    /history
GET    /jobs
GET    /resumes
GET    /jobs/{job_id}/questions

POST   /jobs/analyze
POST   /jobs/upload
POST   /resumes/upload
POST   /questions/generate
POST   /sessions

PATCH  /sessions/{session_id}
DELETE /sessions/{session_id}

POST   /responses/evaluate-text
POST   /responses/evaluate-audio
POST   /responses/transcribe-audio
```

---

# Android Mobile App Configuration

Before releasing the Android app, configure the backend base URL:

```text
https://your-app-name.azurewebsites.net
```

Do not use local development addresses in production:

```text
http://10.0.2.2:8000
http://localhost:8000
```

These only work for local emulator or local machine testing.

---

# Local Development

Set environment variables first:

```powershell
$env:DATABASE_URL="your_supabase_postgres_url"
$env:OPENAI_LLM_API_KEY="your_openai_key"
$env:OPENAI_WHISPER_API_KEY="your_openai_key"
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Run FastAPI locally:

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

---

# Local API Test

Test the health endpoint:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Expected response:

```json
{
  "status": "ok"
}
```

---

# Azure Deployment Test

After deployment completes and the app restarts:

```powershell
$base = "https://your-app-name.azurewebsites.net"

Invoke-RestMethod "$base/health"
Invoke-RestMethod "$base/ai/status" | ConvertTo-Json -Depth 10
```

Expected `/health` response:

```json
{
  "status": "ok"
}
```

---

# Notes

* Azure Free Tier may experience cold starts after inactivity.
* Linux Web App is strongly recommended for FastAPI deployments.
* Azure automatically installs dependencies from `requirements.txt`.
* Use PostgreSQL (such as Supabase) instead of SQLite for production deployments.
* Whisper audio uploads may increase memory usage on lower pricing tiers.
