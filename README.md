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
- **Redis** (Upstash) — distributed locking, login rate limiting and the token denylist
- **Alembic** — database migrations
- **Pydantic v2** — request/response validation
- **JWT** authentication (access + refresh tokens, with revocation and refresh token rotation)
- **pytest** — 108 automated tests, including real concurrency tests using `asyncio.gather`
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
│   │   ├── token_revocation.py
│   │   ├── pagination.py
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
│   │   ├── auth_service.py
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
│   │   ├── 1eb1b7b3025a_add_indexes_to_schedulings_table.py
│   │   └── a3f9c2d41b7e_make_client_phone_optional.py
│   ├── env.py
│   ├── README
│   └── script.py.mako
│
├── scripts/
│   └── reset_password.py
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_token_revocation.py
│   ├── test_password.py
│   ├── test_clients.py
│   ├── test_services.py
│   ├── test_pagination.py
│   ├── test_scheduling.py
│   └── test_scheduling_status.py
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
└── requirements.txt
```

The business logic in `services/scheduling_service.py` is kept separate from the HTTP layer in `routers/`, so the scheduling rules can be tested directly without going through the API, and so the router layer stays focused on translating between HTTP and business exceptions. `clients` and `services` don't have a dedicated service layer, since they're simple CRUD without rules complex enough to justify one.

---

## Key design decisions

- **Redis distributed lock** around scheduling creation, using a single fixed global key (not one per time slot), since there's only one professional and the entire schedule is one contended resource. This guards against concurrent *requests*, not concurrent *users* — the same single account can still generate overlapping requests (double-click, multiple open tabs/devices, a network retry). Verified with a concurrency test that fires two simultaneous requests for the same time slot and confirms exactly one succeeds.
- **Evaluation-to-procedure flow**: an evaluation appointment (fixed 1h) can be linked to a later procedure appointment for services that require one. Completing the evaluation records the real estimated duration (5-8h), which the linked procedure then uses to calculate its own end time. An evaluation can only be used once, and only for a confirmed (non-cancelled) evaluation of the matching client and service — an evaluation whose time has already passed (reported as `completed`, see below) still counts as confirmed.
- **Login rate limiting** (5 failed attempts triggers a 5-minute lockout) is backed by Redis but fails open if Redis is unavailable — a Redis outage degrades this specific protection rather than blocking legitimate logins entirely.
- **Timezone handling**: all scheduling times are normalized to `Europe/Lisbon`, regardless of the timezone the client sends, so business-hour and past-date validation always compares against the salon's real wall-clock time.
- **Test isolation**: the test suite uses a separate local PostgreSQL database. Each test runs inside a nested SAVEPOINT transaction — application code can call `commit()` normally (as every endpoint does) without ever ending the outer transaction, which is rolled back after each test. This gives true per-test isolation without mocking the database layer.
- **Token revocation** via a Redis denylist. Every token carries a unique `jti`; a revoked `jti` is stored with a TTL equal to the token's remaining lifetime, so the key deletes itself once the token would have expired anyway. Logout revokes the current access token (and the refresh token, if sent).
- **Refresh token rotation**: each refresh token can be exchanged exactly once. The old token is marked as used atomically (`SET ... NX EX`) before the new pair is issued, so if two refresh requests with the same token arrive at the same time, one succeeds and the other gets `401`. A client must therefore store the new refresh token from every response and not refresh from two tabs in parallel.
- **Denylist failure policy** when Redis is unavailable:
  - *Access tokens fail open*: valid, unexpired access tokens are still accepted. They live at most 30 minutes, and rejecting everything would lock the only user out over a defense-in-depth check — the same trade-off as login rate limiting. The cost: during an outage, a token revoked by logout or a password change keeps working until it expires.
  - *Refresh and logout fail closed*: a refresh is refused (`401`) because refresh tokens are long-lived (7 days), and logout returns `503` instead of pretending the tokens were revoked. Logging in with the password still works.
- **Password change** (`POST /auth/change-password`) invalidates every token issued before it: the denylist stores a per-user "revoked before" timestamp, compared against each token's `iat`. A wrong current password returns `403` (not `401`), since the user is authenticated and a `401` would look like an expired session to the frontend. Password rule: at least 8 characters, at least one letter and one digit, at most 72 bytes (bcrypt ignores anything beyond that).
- **`COMPLETED` is a derived status, not a persisted one.** The database keeps `confirmed`; the API reports `completed` for a confirmed scheduling whose end time has passed, through a single helper (`effective_status`). Because the stored status never changes, every rule that reads it behaves the same: a past confirmed scheduling still blocks deleting its client or service (protecting the history), a past evaluation can still be completed and linked to a procedure, and a past scheduling can still be cancelled (e.g. to record a no-show). `completed` only means the time slot has passed, not that the service was actually delivered.
- **Pagination**: `GET /clients`, `GET /services` and `GET /schedulings` accept `skip` (default `0`) and `limit` (default `1000`, max `5000`), are ordered by `id`, and return the total count of matching records in the `X-Total-Count` header (exposed through CORS). The body stays a plain list, and the default limit is generous enough that a small salon's frontend still receives everything in one request.

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
3. Use `POST /auth/refresh` with the refresh token to obtain a new token pair once the access token expires. The refresh token is single-use: always keep the new one from the response
4. `POST /auth/logout` (authenticated, optional JSON body `{"refresh_token": "..."}`) revokes the current access token and, if sent, the refresh token
5. `POST /auth/change-password` (authenticated, JSON body `{"current_password": "...", "new_password": "..."}`) changes the password, revokes every older token and returns a new token pair

If the password is lost, it can be reset from the command line with the versioned admin script below (unlike the account creation script, this one is part of the repository). It shows the target database host and asks for confirmation, reads the new password with `getpass`, and never prints passwords or hashes:

```bash
python -m scripts.reset_password owner@example.com
```

### Pagination

List endpoints take `skip` and `limit` query params, e.g. `GET /schedulings?skip=0&limit=100`. `limit` defaults to `1000` and is capped at `5000` (larger values return `422`). The total number of matching records (respecting filters such as `date`) is returned in the `X-Total-Count` response header.

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

108 tests covering:
- **Auth**: login success/failure, email normalization, refresh token validation (including rejecting an access token used as a refresh token), and rate limiting
- **Token revocation**: logout, refresh token rotation (including two concurrent refreshes with the same token), legacy tokens without `jti`, key expiry by TTL, and the Redis failure policy (simulated outage)
- **Password**: change password (correct/wrong current password, weak passwords, revoking older tokens) and the reset function used by the admin script
- **Clients / Services**: full CRUD, auth enforcement, field validation, pagination and `X-Total-Count`
- **Scheduling**: business hours, evaluation requirement, the full evaluation-to-procedure flow, evaluation reuse prevention, overlap detection, the 24-hour cancellation window, the concurrency test described above, and the derived `completed` status

The tests also use the Redis instance from `REDIS_URL`. Keys created by the tests use a `test:` prefix and a short TTL and are deleted by exact name after each test — never by pattern or `FLUSHDB`. The scheduling concurrency test does use the real global lock key, though (see Known limitations).

---

## Deployment

- **API**: Docker container on [Render](https://render.com) (Frankfurt region), built directly from the repository's `Dockerfile`
- **Database**: [Supabase](https://supabase.com) — managed PostgreSQL (Frankfurt region)
- **Cache / locking**: [Upstash](https://upstash.com) — managed Redis (Frankfurt region)

All three services run in the same region to minimize latency between them. Environment variables are configured directly on Render and are never baked into the Docker image — `.dockerignore` explicitly excludes `.env`, `venv/`, and other files that shouldn't ship inside the container.

---

## Known limitations / next steps

Current limitations, accepted deliberately for a single salon with a single account:

- **No self-service password recovery** — there is no email provider, so there's no "forgot password" link. A logged-in user can change the password via `POST /auth/change-password`; a lost password is reset with `scripts/reset_password.py`, which needs direct database access. An email-based reset flow is worth adding if more users are ever added.
- **Tokens issued before revocation was introduced** have no `jti`, so they can't be revoked individually and stay valid until they expire (at most 7 days after the deploy, the refresh token lifetime). A password change still invalidates them.
- **Revocation is not enforced for access tokens while Redis is down** — the fail-open policy described in Key design decisions. A revoked access token keeps working until it expires (at most 30 minutes) during an outage.
- **`completed` is derived from the clock, not recorded** — it means the time slot has passed, not that the appointment actually took place; a no-show stays `completed` unless it's cancelled. There's no way to filter by status in the database, and a confirmed past scheduling still blocks deleting its client or service.
- **Pagination keeps a plain list body** — a client that doesn't send `limit` gets at most 1000 records, ordered by `id` (oldest first), so beyond that the newest ones are left out; `X-Total-Count` is how a client can detect it.
- **Tests share the application's Redis instance** — test keys are isolated by prefix, but the scheduling concurrency test uses the real global lock key (`lock:scheduling:create`), so a test run can briefly block, or be blocked by, a real booking. A separate `TEST_REDIS_URL` would remove that coupling.

---

## License

See [`LICENSE`](./LICENSE).
