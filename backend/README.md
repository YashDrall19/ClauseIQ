# Contract Analysis API

FastAPI service that extracts text from PDF, DOCX, and TXT contracts locally and sends bounded, page-labelled excerpts to Gemini or OpenAI for structured answers. The API key is server-only; never put it in the React application.

## Run locally

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

For tests, install `pip install -r requirements-dev.txt` and run `pytest -q`.

Set the provider and one key in `.env`:

```dotenv
AI_PROVIDER=gemini
GEMINI_API_KEY=your_key
GEMINI_MODEL=gemini-flash-lite-latest
```

For OpenAI, use `AI_PROVIDER=openai`, `OPENAI_API_KEY`, and `OPENAI_MODEL` instead. Scanned PDFs also require Tesseract installed on the host.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Database and provider-key readiness |
| POST | `/api/contracts/upload` | Extract, store, and immediately answer the five standard questions |
| POST | `/api/contracts/{id}/analyze` | Return the five standard contract insights |
| POST | `/api/contracts/{id}/chat` | Ask a grounded follow-up question |
| GET | `/api/contracts` | List stored contracts |
| GET / DELETE | `/api/contracts/{id}` | Read metadata or permanently delete a contract |

## Deployment

Use a persistent mounted volume for `/app/storage`, set `CORS_ORIGINS` to the exact deployed frontend origin, and set the provider key as a host secret/environment variable. Do not deploy the default SQLite design for multiple API instances; use a managed database and object storage before scaling horizontally.

This API has no user authentication. Do not expose it publicly until an authentication and authorization layer is added; an unauthenticated public endpoint can expose uploaded contracts and consume your AI-provider budget.
