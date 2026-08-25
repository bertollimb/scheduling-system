# Scheduling System

A backend API for managing appointments at a hair salon, built as a real-world portfolio project — not a tutorial exercise. It solves an actual scheduling problem for a single-professional salon: preventing double-bookings, enforcing business hours, and handling services that require a prior in-person evaluation before a variable-duration procedure can be booked.

**Live API docs:** https://scheduling-system-vmfx.onrender.com/docs

---

## Table of contents

- [The problem](#the-problem)
- [Tech stack](#tech-stack)
- [Architecture](#architecture)
- [Key design decisions](#key-design-decisions)
- [Getting started](#getting-started)
- [Running with Docker](#running-with-docker)
- [Running the test suite](#running-the-test-suite)
- [Deployment](#deployment)
- [Known limitations / next steps](#known-limitations--next-steps)
- [License](#license)

---

## The problem

Only one person (the salon owner) uses this system — but a single user can still trigger two nearly-simultaneous requests for the same time slot: a double-click on "confirm", the same account open in two tabs or on two devices at once, or a network retry after a slow response. Race conditions are a property of how many requests hit the server at once, not how many people are logged in — so the system still needs to defend against it. Some services (hair treatments, straightening) can also take 5 to 8 hours and require an in-person evaluation before the actual procedure is scheduled, since the exact duration depends on the client's hair, while other services (cuts, color) have a fixed, predictable duration. The system needs to:

- Prevent overlapping time slots from ever being double-booked, even when two requests for the same slot arrive at nearly the same instant
- Enforce that long procedures always start at opening time
- Require and track a completed evaluation before allowing its linked procedure to be booked
- Enforce business hours (Tuesday-Saturday, 10:00-19:00) and a 24-hour cancellation window
- Rate-limit login attempts to protect the single account that has access to the system

---

## Tech stack

- **Python 3.13** / **FastAPI**
- **PostgreSQL** (Supabase) with **SQLAlchemy 2.0**, fully async
- **Redis** (Upstash) — distributed locking and login rate limiting
- **Alembic** — database migrations
- **Pydantic v2** — request/response validation
- **JWT** authentication (access + refresh tokens)
- **pytest** — 42 automated tests, including a real concurrency test using `asyncio.gather`
- **Docker** — containerized deployment
- Deployed on **Render**, database and cache on **Supabase**/**Upstash**

---

## Architecture

```
scheduling-system/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── configs.py
│   │   ├── deps.py
│   │   ├── security.py
│   │   └── exceptions.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── session.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user_model.py
│   │   ├── client_model.py
│   │   ├── service_model.py
│   │   └── scheduling_model.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── auth_schema.py
│   │   ├── client_schema.py
│   │   ├── service_schema.py
│   │   └── scheduling_schema.py
│   ├── services/
│   │   ├── __init__.py
│   │   └── scheduling_service.py
│   └── routers/
│       ├── __init__.py
│       ├── auth_router.py
│       ├── client_router.py
│       ├── service_router.py
│       └── scheduling_router.py
│
├── alembic/
│   ├── versions/
│   │   ├── 73684d6ad4a8_create_initial_tables.py
│   │   └── 1eb1b7b3025a_add_indexes_to_schedulings_table.py
│   ├── env.py
│   ├── README
│   └── script.py.mako
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_clients.py
│   ├── test_services.py
│   └── test_scheduling.py
│
├── .dockerignore
├── .env.example
├── .gitattributes
├── .gitignore
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── LICENSE
├── pytest.ini
├── README.md
├── requirements.txt
└── TODO.md
```

The business logic in `services/scheduling_service.py` is kept separate from the HTTP layer in `routers/`, so the scheduling rules can be tested directly without going through the API, and so the router layer stays focused on translating between HTTP and business exceptions. `clients` and `services` don't have a dedicated service layer, since they're simple CRUD without rules complex enough to justify one.

---

## Key design decisions

- **Redis distributed lock** around scheduling creation, using a single fixed global key (not one per time slot), since there's only one professional and the entire schedule is one contended resource. This guards against concurrent *requests*, not concurrent *users* — the same single account can still generate overlapping requests (double-click, multiple open tabs/devices, a network retry). Verified with a concurrency test that fires two simultaneous requests for the same time slot and confirms exactly one succeeds.
- **Evaluation-to-procedure flow**: an evaluation appointment (fixed 1h) can be linked to a later procedure appointment for services that require one. Completing the evaluation records the real estimated duration (5-8h), which the linked procedure then uses to calculate its own end time. An evaluation can only be used once, and only for a confirmed (non-cancelled) evaluation of the matching client and service.
- **Login rate limiting** (5 failed attempts triggers a 5-minute lockout) is backed by Redis but fails open if Redis is unavailable — a Redis outage degrades this specific protection rather than blocking legitimate logins entirely.
- **Timezone handling**: all scheduling times are normalized to `Europe/Lisbon`, regardless of the timezone the client sends, so business-hour and past-date validation always compares against the salon's real wall-clock time.
- **Test isolation**: the test suite uses a separate local PostgreSQL database. Each test runs inside a nested SAVEPOINT transaction — application code can call `commit()` normally (as every endpoint does) without ever ending the outer transaction, which is rolled back after each test. This gives true per-test isolation without mocking the database layer.
- **No pagination, password recovery, or token revocation yet** — deliberate scope decisions for a single-user system at this stage. See [Known limitations](#known-limitations--next-steps).

---

## Getting started

### Prerequisites

- Python 3.13+
- A PostgreSQL database (this project uses [Supabase](https://supabase.com))
- A Redis instance (this project uses [Upstash](https://upstash.com))

### Local setup

```bash
git clone https://github.com/bertollimb/scheduling-system.git
cd scheduling-system
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in the required values:

```
DB_URL=postgresql+asyncpg://...
REDIS_URL=rediss://...
JWT_SECRET=
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
```

Apply migrations and run the server:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000/docs` (Swagger UI).

### Authentication

There's no public sign-up endpoint, since only one account (the salon owner) is expected to ever exist. The account is created once, directly against the database, via a local script (not committed to the repository).

1. Log in via `POST /auth/login` (OAuth2 password flow — username/password as form data) to receive an access token and a refresh token
2. Send the access token on protected endpoints:
```
   Authorization: Bearer <access_token>
```
3. Use `POST /auth/refresh` with the refresh token to obtain a new token pair once the access token expires

---

## Running with Docker

```bash
docker-compose up --build
```

The container reads the same `.env` file as local development. `DB_URL` and `REDIS_URL` point to the managed Supabase/Upstash instances, so no local database or cache container is needed — `docker-compose.yml` only defines the `api` service.

---

## Running the test suite

Requires a separate local PostgreSQL database for tests (set `TEST_DB_URL` in `.env` — this database is never touched by the main application):

```bash
pytest -v
```

44 tests covering:
- **Auth**: login success/failure, email normalization, refresh token validation (including rejecting an access token used as a refresh token), and rate limiting
- **Clients / Services**: full CRUD, auth enforcement, field validation
- **Scheduling**: business hours, evaluation requirement, the full evaluation-to-procedure flow, evaluation reuse prevention, overlap detection, the 24-hour cancellation window, and the concurrency test described above

---

## Deployment

- **API**: Docker container on [Render](https://render.com) (Frankfurt region), built directly from the repository's `Dockerfile`
- **Database**: [Supabase](https://supabase.com) — managed PostgreSQL (Frankfurt region)
- **Cache / locking**: [Upstash](https://upstash.com) — managed Redis (Frankfurt region)

All three services run in the same region to minimize latency between them. Environment variables are configured directly on Render and are never baked into the Docker image — `.dockerignore` explicitly excludes `.env`, `venv/`, and other files that shouldn't ship inside the container.

---

## Known limitations / next steps

A few scope gaps were documented deliberately rather than implemented immediately, since they don't affect the system's correctness for its current real-world use case (a single salon, a single account). Full details in [`TODO.md`](./TODO.md):

- **Pagination** — list endpoints return the full result set; fine at the current data volume, worth revisiting if it grows significantly
- **Password recovery** — resetting the account password currently requires a manual script; no self-service flow yet
- **Token revocation** — JWTs are stateless, so a leaked refresh token can't be invalidated before it expires
- **Scheduling completion status** — the `COMPLETED` status exists in the model but nothing currently transitions a scheduling into it once its time has passed

---

## License

See [`LICENSE`](./LICENSE).
