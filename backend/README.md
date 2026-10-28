# JobPilot AI — Backend API

FastAPI application that powers the JobPilot AI autonomous career agent system.

For Sprint 2 durable execution, apply the new migrations, set `EXECUTION_MODE=durable` on API and worker, and start `python -m app.workers.runner` alongside the API. Full setup and recovery details are in [SPRINT_2_STATUS.md](../SPRINT_2_STATUS.md). `docker-compose.durable.yml` provides the two processes without Redis; the original Compose file remains the legacy configuration.

## Setup Instructions

### Local Development (Python Virtual Environment)
1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # macOS/Linux:
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy the sample environment file and fill in your keys:
   ```bash
   cp .env.example .env
   ```
5. Run the FastAPI development server:
   ```bash
   python -m uvicorn app.main:app --reload
   ```
6. Access the interactive API docs at `http://localhost:8000/docs`.

### Docker Development
To spin up the FastAPI app along with Redis for background tasks:
1. Ensure Docker is running.
2. Build and start containers:
   ```bash
   docker-compose up --build
   ```
3. Access API docs at `http://localhost:8000/docs` and the API itself.
