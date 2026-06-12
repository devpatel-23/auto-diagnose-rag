#  AutoMechAI — Vehicle Repair & Restoration Chatbot

An industry-grade AI chatbot for vehicle repair, diagnostics, and classic restoration. Built with FastAPI, PostgreSQL + pgvector, OpenAI GPT-4o, and Chainlit.

---

## Architecture

```
User (Browser)
    │
    ▼
Chainlit UI (frontend/app.py)
    │  HTTP POST with message
    ▼
FastAPI Backend (backend/main.py)
    │
    ├── Vector Search ──────► PostgreSQL + pgvector
    │   (find relevant docs)    (repair_documents table)
    │
    ├── History Fetch ──────► PostgreSQL
    │   (last 10 messages)      (chat_messages table)
    │
    └── LLM Call ───────────► OpenAI GPT-4o
        (generate response)     (streamed back)
            │
            ▼
        Stream back through FastAPI → Chainlit → User
```

## 📁 Project Structure

```
vehicle-repair-chatbot/
├── backend/
│   ├── config.py                  # All settings from .env
│   ├── main.py                    # FastAPI app, startup, routing
│   ├── models/
│   │   └── database.py            # SQLAlchemy models (tables)
│   ├── services/
│   │   ├── vector_store.py        # Embeddings, pgvector search
│   │   └── chat_service.py        # RAG pipeline, OpenAI streaming
│   └── routers/
│       ├── chat.py                # /api/chat endpoints
│       └── admin.py               # /admin/health, /admin/ingest
├── frontend/
│   ├── app.py                     # Chainlit UI
│   ├── chainlit.md                # Welcome screen content
│   └── .chainlit/config.toml     # Theme and settings
├── data/
│   └── repair_docs/               # Knowledge base text files
│       ├── 01_engine_diagnostics.txt
│       ├── 02_transmission_drivetrain.txt
│       ├── 03_brakes_suspension_steering.txt
│       ├── 04_electrical_systems.txt
│       ├── 05_vehicle_restoration.txt
│       ├── 06_obd_codes_database.txt
│       └── 07_maintenance_schedules.txt
├── scripts/
│   ├── setup_db.py                # One-time DB initialization
│   ├── ingest.py                  # Load docs into vector store
│   └── test_system.py             # Full system health test
├── .env.example                   # Template for environment variables
├── requirements.txt
├── render.yaml                    # Render.com deployment config
└── README.md
```

---

##  Setup Guide (Step by Step)

### Prerequisites

- Python 3.11+
- PostgreSQL 14+ with pgvector extension
- OpenAI API key (get from platform.openai.com)

### Option A: Local Development

#### Step 1 — Clone and install dependencies

```bash
git clone <your-repo>
cd vehicle-repair-chatbot
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

#### Step 2 — Set up environment variables

```bash
cp .env.example .env
# Now edit .env with your actual values
```

Your `.env` file should look like:
```
OPENAI_API_KEY=sk-your-actual-key
DATABASE_URL=postgresql://postgres:password@localhost:5432/vehicle_repair_bot
APP_ENV=development
SECRET_KEY=any-random-string-here
```

#### Step 3 — Set up PostgreSQL with pgvector

```bash
# Create the database
psql -U postgres -c "CREATE DATABASE vehicle_repair_bot;"

# Install pgvector (if not already installed)
# On Ubuntu/Debian:
sudo apt install postgresql-14-pgvector

# On Mac with Homebrew:
brew install pgvector

# Initialize the database tables
python scripts/setup_db.py
```

#### Step 4 — Ingest repair documents

This reads all files in `data/repair_docs/`, splits them into chunks,
calls OpenAI embeddings API, and stores everything in pgvector.

```bash
python scripts/ingest.py
```

Expected output:
```
Found 7 documents to process:
  📄 01_engine_diagnostics.txt (8,432 bytes)
  📄 02_transmission_drivetrain.txt (6,218 bytes)
  ...
✅ Files processed:  7/7
✅ Chunks stored:    142
⏱️  Time taken:      23.4 seconds
```

#### Step 5 — Test the system

```bash
python scripts/test_system.py
```

All 5 tests should pass.

#### Step 6 — Run the application

Open **two terminals**:

Terminal 1 — Backend API:
```bash
uvicorn backend.main:app --reload --port 8000
```

Terminal 2 — Frontend:
```bash
chainlit run frontend/app.py
```

Open http://localhost:8000 for the Chainlit chat UI.
Open http://localhost:8000/docs for the API documentation.

---

### Option B: Deploy to Render.com

#### Step 1 — Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/yourusername/vehicle-repair-chatbot.git
git push -u origin main
```

#### Step 2 — Create Render services

1. Go to render.com → New → Blueprint
2. Connect your GitHub repo
3. Render reads `render.yaml` and creates all services automatically

#### Step 3 — Set environment variables in Render

In the Render dashboard for the API service, add:
- `OPENAI_API_KEY` = your OpenAI key

All other variables are set in render.yaml automatically.

#### Step 4 — Run ingestion on Render

After deployment, call the ingestion endpoint:
```bash
curl -X POST https://your-api.onrender.com/admin/ingest/sync
```

Or use the Render shell feature to run:
```bash
python scripts/ingest.py
```

---

## API Reference

### Chat

```
POST /api/chat
Body: {"message": "string", "session_id": "optional-string"}
Returns: {"response": "string", "session_id": "string"}
```

```
POST /api/chat/stream
Body: {"message": "string", "session_id": "optional-string"}
Returns: Server-Sent Events stream
```

### History

```
GET /api/history/{session_id}
Returns: {"session_id": "...", "messages": [...]}
```

### Admin

```
GET  /admin/health          → System health check
POST /admin/ingest          → Trigger background ingestion
POST /admin/ingest/sync     → Trigger and wait for ingestion
GET  /admin/stats           → System statistics
```

---

##  How RAG Works

1. **Ingestion** (one-time setup):
   - Read repair manual text files
   - Split into ~1000 character chunks with 200 char overlap
   - Send each chunk to OpenAI text-embedding-3-small
   - Receive a 1536-dimensional vector for each chunk
   - Store (text, vector) pairs in PostgreSQL/pgvector

2. **Inference** (every chat message):
   - Embed the user's question into a vector
   - Use pgvector's `<=>` operator to find the 5 most similar chunks
   - Add those chunks as context in the LLM prompt
   - GPT-4o answers using both its training AND the retrieved context

This gives accurate, specific answers about vehicles even if GPT wasn't
trained on that exact information.

---


Good sources for repair knowledge:
- Factory service manuals (legal to use for learning)
- Mitchell1, AllData documentation
- iATN technical articles
- Vehicle-specific forums and wikis

---
