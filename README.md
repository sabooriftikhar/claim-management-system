# Claim Management System

A production-style claims processing platform for managing submissions from intake through review, decision, settlement, and closure. The project combines a modular FastAPI backend with a Next.js dashboard and PostgreSQL persistence.

It is designed as a generic product-company claims system that can support warranty claims, damaged shipments, reimbursements, and similar workflows without being tied to a single insurance domain.

## Features

- JWT authentication with access and refresh tokens
- Role-based access control for claimants, adjusters, and administrators
- Claim creation, submission, assignment, review, approval, rejection, settlement, and closure
- Enforced claim status transitions with a complete status history
- Document uploads and evidence management
- In-app notifications for claim activity
- Admin user and role management
- Admin analytics for claim counts and resolution time
- Rate limiting on authentication endpoints
- API error handling, CORS configuration, health checks, and OpenAPI documentation
- Demo seed data for local development

## Claim Lifecycle

```text
Draft -> Submitted -> In Review -> Approved/Rejected
								  |
							  Approved -> Settled -> Closed
```

Every status change is recorded in the claim history and can trigger a notification for the relevant users.

## Roles

| Role | Capabilities |
| --- | --- |
| Claimant | Create claims, upload evidence, track owned claims, and view notifications |
| Adjuster | Review assigned claims, inspect documents, make decisions, and progress claims |
| Admin | Manage users and roles, view all claims, and access analytics |

## Architecture

```mermaid
flowchart LR
	Browser[Next.js dashboard] -->|HTTPS / JSON / JWT| API[FastAPI API]
	API --> DB[(PostgreSQL)]
	API --> Migrations[Alembic migrations]
	Browser --> UI[TypeScript + Tailwind UI]
```

### Backend modules

The backend is organized by feature under `backend/app/modules/`:

- `auth` - registration, login, refresh, logout, and password security
- `users` - current-user profile and user access
- `claims` - claim lifecycle and ownership rules
- `documents` - claim evidence and file metadata
- `reviews` - assignment and review decisions
- `notifications` - user notifications
- `admin` - analytics and role administration

## Technology Stack

- **Backend:** Python, FastAPI, SQLAlchemy async, asyncpg, Alembic, Pydantic
- **Database:** PostgreSQL
- **Frontend:** Next.js 14, React, TypeScript, Tailwind CSS
- **Charts:** Recharts
- **Authentication:** JWT with bcrypt password hashing
- **Deployment target:** Render for the API and database, Vercel for the frontend

## Local Setup

### Prerequisites

- Python 3.11 or newer
- Node.js 18 or newer
- PostgreSQL

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a `backend/.env` file:

```env
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/claims_db
JWT_SECRET=replace-with-a-long-random-secret
JWT_REFRESH_SECRET=replace-with-another-long-random-secret
CORS_ORIGINS=http://localhost:3000
APP_ENV=development
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
```

Run the API:

```powershell
uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`. Interactive documentation is available at `http://localhost:8000/docs`.

For a clean database or demo data, use the migration and seed commands from the `backend` directory:

```powershell
alembic upgrade head
python seed.py
```

### Frontend

```powershell
cd frontend
npm install
```

Create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Start the dashboard:

```powershell
npm run dev
```

Open `http://localhost:3000` in a browser.

## Useful Commands

| Command | Purpose |
| --- | --- |
| `uvicorn app.main:app --reload` | Start the development API |
| `alembic upgrade head` | Apply database migrations |
| `python seed.py` | Populate local demo data |
| `pytest` | Run backend tests |
| `npm run dev` | Start the Next.js development server |
| `npm run build` | Create a production frontend build |

## Project Status

The core authentication, claim workflow, documents, reviews, notifications, audit timeline, admin management, and analytics features are implemented. The payment or settlement provider is intentionally represented as a workflow state rather than a real payment integration, leaving room for a future Stripe or PayPal adapter.