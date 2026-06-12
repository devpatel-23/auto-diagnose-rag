#!/usr/bin/env bash
# start_dev.sh
# -------------
# One-command local development setup and launch.
# Run this from the project root after completing initial setup.
#
# USAGE:
#   chmod +x start_dev.sh     (first time only — makes it executable)
#   ./start_dev.sh            (starts everything)
#   ./start_dev.sh --setup    (first time — creates venv, installs deps, sets up DB)
#
# WHAT IT DOES:
# 1. Activates virtual environment
# 2. Starts PostgreSQL via Docker
# 3. Initializes DB if needed
# 4. Runs ingestion if vector store is empty
# 5. Starts FastAPI backend in background
# 6. Starts Chainlit frontend in foreground

set -e  # Exit immediately on any error

# ── Colors for output ─────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'  # No color

log_info()    { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }
log_section() { echo -e "\n${BLUE}════════════════════════════════${NC}"; echo -e "${BLUE}  $1${NC}"; echo -e "${BLUE}════════════════════════════════${NC}"; }

# ── Check we're in the right directory ────────────────────
if [ ! -f "requirements.txt" ]; then
    log_error "Run this script from the project root directory (where requirements.txt is)"
    exit 1
fi

# ── First-time setup ──────────────────────────────────────
if [ "$1" == "--setup" ]; then
    log_section "First-Time Setup"

    # Check .env exists
    if [ ! -f ".env" ]; then
        log_info "Creating .env from template..."
        cp .env.example .env
        log_warn "⚠️  Please edit .env and add your OPENAI_API_KEY before continuing"
        log_warn "    Then re-run: ./start_dev.sh --setup"
        exit 0
    fi

    # Create virtual environment
    if [ ! -d "venv" ]; then
        log_info "Creating Python virtual environment..."
        python3 -m venv venv
    fi

    # Activate venv
    source venv/bin/activate

    # Install dependencies
    log_info "Installing Python dependencies..."
    pip install --upgrade pip --quiet
    pip install -r requirements.txt --quiet

    log_info "Dependencies installed ✅"

    # Start Docker Postgres
    log_info "Starting PostgreSQL via Docker..."
    docker-compose up -d postgres
    log_info "Waiting for PostgreSQL to be ready..."
    sleep 5

    # Setup database
    log_info "Setting up database tables..."
    python scripts/setup_db.py

    # Run ingestion
    log_info "Ingesting repair documents..."
    python scripts/ingest.py

    # Run tests
    log_info "Running system tests..."
    python scripts/test_system.py

    log_section "Setup Complete!"
    log_info "Run './start_dev.sh' to start the application"
    exit 0
fi

# ── Normal Start ──────────────────────────────────────────
log_section "AutoMechAI — Local Development"

# Check .env exists
if [ ! -f ".env" ]; then
    log_error ".env file not found. Run: ./start_dev.sh --setup"
    exit 1
fi

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
    log_info "Virtual environment activated"
else
    log_warn "No venv found — using system Python"
fi

# Start PostgreSQL
log_info "Starting PostgreSQL..."
docker-compose up -d postgres 2>/dev/null || log_warn "Docker not running or postgres already up"
sleep 2

# Start FastAPI backend in background
log_info "Starting FastAPI backend on http://localhost:8000 ..."
uvicorn backend.main:app --reload --port 8000 --log-level warning &
BACKEND_PID=$!
log_info "Backend PID: $BACKEND_PID"
sleep 2

# Check backend started
if ! curl -s http://localhost:8000/admin/health > /dev/null 2>&1; then
    log_warn "Backend may not have started yet — check for errors above"
fi

log_info "API docs available at: http://localhost:8000/docs"

# Start Chainlit frontend in foreground
log_section "Starting Chainlit UI"
log_info "Chat UI will open at: http://localhost:8080"
log_info "Press Ctrl+C to stop all services"

# Trap Ctrl+C to clean up background processes
trap "log_info 'Stopping services...'; kill $BACKEND_PID 2>/dev/null; exit 0" INT TERM

chainlit run frontend/app.py --port 8080

# If chainlit exits, kill backend too
kill $BACKEND_PID 2>/dev/null
