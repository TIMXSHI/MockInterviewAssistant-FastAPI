# Mock Interview Assistant API

Azure Web App API host for the Mock Interview Assistant mobile app.

This deployment hosts only the backend API. The Android app and web frontend do not need to be deployed to this Azure Web App.

## Azure Runtime

Use an Azure Web App with:

```text
Operating system: Linux
Runtime stack: Python 3.14
```

The hosted app runs FastAPI from:

```text
backend/app/main.py
```

The mobile app calls the Azure URL directly:

```text
https://your-app-name.azurewebsites.net
```

## Files To Push To GitHub

For the Azure API repo, include:

```text
backend/
requirements.txt
README.md
.gitignore
```

Do not include:

```text
android/
frontend/
node_modules/
frontend/node_modules/
.env
backend/.env
backend/data/
*.log
.idea/
```

The old Windows/Node files are not needed for the Linux Python Web App:

```text
app.js
package.json
package-lock.json
startup.sh
web.config
```

## Azure Startup Command

In Azure Portal, go to:

```text
Web App > Configuration > General settings > Startup Command
```

Set the startup command to:

```bash
cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

## Azure App Settings

Add these in:

```text
Azure Portal > Web App > Configuration > Application settings
```

Required:

```text
DATABASE_URL=postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres?sslmode=require
OPENAI_LLM_API_KEY=your_openai_key
OPENAI_WHISPER_API_KEY=your_openai_key
CORS_ORIGINS=*
```

You may use `SUPABASE_DATABASE_URL` instead of `DATABASE_URL`.

Do not commit API keys, database passwords, or `.env` files to GitHub.

## API Endpoints

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

## Mobile App Configuration

Before publishing the Android app, set its backend base URL to your Azure Web App URL:

```text
https://your-app-name.azurewebsites.net
```

Do not use these for the published app:

```text
http://10.0.2.2:8000
http://localhost:8000
```

Those only work for local development.

## Local API Test

For local testing, set environment variables first:

```powershell
$env:DATABASE_URL="your_supabase_postgres_url"
$env:OPENAI_LLM_API_KEY="your_openai_key"
$env:OPENAI_WHISPER_API_KEY="your_openai_key"
pip install -r requirements.txt
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

Then test:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Expected response:

```json
{
  "status": "ok"
}
```

## Azure Test

After deployment and restart:

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
