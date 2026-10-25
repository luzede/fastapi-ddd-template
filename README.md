# FastAPI DDD Template

An async FastAPI service template organised by **feature modules** (a pragmatic,
domain-driven layout), with production concerns already wired in:

- **Async PostgreSQL** via SQLAlchemy 2.0 + asyncpg, with a generic repository and Alembic migrations
- **Email/password auth**: Argon2id hashing (pwdlib) and HS256 JWT access tokens (PyJWT)
- **RFC 9457 Problem Details** for every error response, documented in OpenAPI
- **Structured logging** (structlog + stdlib) with automatic secret redaction
- **OpenTelemetry** traces and logs, exported over OTLP/HTTP when an endpoint is configured
- **Typed settings** (pydantic-settings) with nested env vars (`DB__HOST`, `AUTH__SECRET`, …)
- **Strict static typing** checked with [Pyrefly](https://pyrefly.org)

> Working on this repo with an AI coding agent? Point it at [AGENTS.md](AGENTS.md).

## Tech stack

| Concern          | Choice                                                     |
| ---------------- | ---------------------------------------------------------- |
| Runtime          | Python **3.14** (managed with [uv](https://docs.astral.sh/uv/)) |
| Web framework    | FastAPI / Starlette, served by Uvicorn                     |
| Database         | PostgreSQL **18+** (`uuidv7()` is used for primary keys)   |
| ORM / migrations | SQLAlchemy 2.0 (async) / Alembic                           |
| Auth             | pwdlib (Argon2id), PyJWT                                   |
| Observability    | structlog, python-json-logger (orjson), OpenTelemetry SDK  |
| Tooling          | Ruff (format + lint), Pyrefly (strict type checking)       |

## Quick start

Prerequisites: [uv](https://docs.astral.sh/uv/getting-started/installation/) and a
running PostgreSQL 18+ instance.

```bash
# 1. Install dependencies (creates .venv and installs Python 3.14 if needed)
uv sync

# 2. Configure the environment
cp .env.example .env
#    Then edit .env. The example is production-flavoured; for local work set at least:
#      ENVIRONMENT=development
#      SERVER__HOST=localhost
#      DB__HOST / DB__USERNAME / DB__PASSWORD / DB__NAME
#      AUTH__SECRET and AUTH__JWT_SECRET (>= 32 chars each)
#    Generate secrets with:  python -c "import secrets; print(secrets.token_urlsafe(48))"

# 3. Apply database migrations
uv run alembic upgrade head

# 4. Run the server (hot-reload is enabled automatically when ENVIRONMENT=development)
uv run python -m app.main
```

Then open:

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>

OpenAPI docs are disabled when `ENVIRONMENT=production`.

> [!NOTE]
> The app uses a factory (`app.main:create_app`), so if you invoke Uvicorn directly you
> must pass `--factory`: `uv run uvicorn app.main:create_app --factory --reload`.

## Configuration

All settings live in [`app/core/config.py`](app/core/config.py) and are loaded from
environment variables or `.env`. Nested groups use a double-underscore delimiter:

| Prefix     | Settings group     | Examples                                                    |
| ---------- | ------------------ | ----------------------------------------------------------- |
| _(none)_   | App                | `ENVIRONMENT`, `LOG_LEVEL`                                  |
| `SERVER__` | `ServerSettings`   | `SERVER__HOST`, `SERVER__PORT`, `SERVER__WORKERS`, `SERVER__CORS_ORIGINS` |
| `DB__`     | `DatabaseSettings` | `DB__HOST`, `DB__USERNAME`, `DB__PASSWORD`, `DB__NAME`, pool sizing |
| `AUTH__`   | `AuthSettings`     | `AUTH__SECRET`, `AUTH__JWT_SECRET`, `AUTH__JWT_EXPIRES_IN`  |
| `OTEL_`    | OpenTelemetry      | `OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`          |

[`.env.example`](.env.example) documents every variable, its default and its production
guidance. `ENVIRONMENT` (`development` | `staging` | `production` | `testing`) drives log
format, default log level, reload/workers and whether API docs are exposed.

## API

| Method | Path                         | Auth   | Description                                  |
| ------ | ---------------------------- | ------ | -------------------------------------------- |
| GET    | `/health/live`               | –      | Liveness probe                               |
| GET    | `/health/ready`              | –      | Readiness probe (checks the database)        |
| POST   | `/api/v1/auth/sign-up/email` | –      | Register with name/email/password → JWT      |
| POST   | `/api/v1/auth/token`         | –      | OAuth2 password form login → JWT             |
| POST   | `/api/v1/auth/change-password` | Bearer | Change password (requires current password) |

Authenticated routes expect `Authorization: Bearer <access_token>`. The Swagger UI
"Authorize" button works out of the box against `/api/v1/auth/token` (use the email as
the username).

### Error format

Every error, including validation errors, unknown routes and unhandled exceptions, is
returned as `application/problem+json` ([RFC 9457](https://www.rfc-editor.org/rfc/rfc9457)):

```json
{
  "type": "https://api.example.com/problems/resource-conflict",
  "title": "Resource Conflict",
  "status": 409,
  "detail": "A user with this email already exists",
  "instance": "/api/v1/auth/sign-up/email",
  "code": "USER_ALREADY_EXISTS",
  "conflicting_field": "email",
  "timestamp": "2026-10-24T12:00:00Z",
  "trace_id": "0af7651916cd43dd8448eb211c80319c"
}
```

`code` values are a stable, closed set (see `ErrorCode` in
[`app/shared/exceptions/enums.py`](app/shared/exceptions/enums.py)) that clients can
branch on. `trace_id` matches the `X-Request-ID` response header and the OpenTelemetry
trace ID.

## Project layout

```text
app/
├── main.py              # App factory: telemetry, logging, handlers, middleware, routers
├── core/                # App-wide config and lifecycle (settings, lifespan, logging, OTel)
├── shared/              # Module-agnostic building blocks
│   ├── db/              #   Declarative Base, async session dependency, generic repository
│   ├── exceptions/      #   RFC 9457 exception hierarchy, handlers, OpenAPI schemas
│   ├── middleware/      #   Trace context (X-Request-ID) and Server-Timing
│   ├── utils/           #   Small pure helpers
│   └── state.py         #   Typed app.state / request.state
└── modules/             # Feature modules (bounded contexts)
    ├── auth/            #   Sign-up / sign-in / password, JWT issue + verification
    ├── user/            #   User model, repository, current-user dependencies
    └── health/          #   Liveness / readiness probes
migrations/              # Alembic (async env; autogenerate reads Base.metadata)
```

Each feature module follows the same shape: `model.py` → `repository.py` →
`service.py` → `router.py`, with `schemas.py` (Pydantic I/O), `dependencies.py`
(FastAPI `Depends` providers) and `types.py` (TypedDicts) as needed.

## Development

```bash
uv run pyrefly check            # strict type checking (must report 0 errors)
uv run ruff format .            # format
uv run ruff check --fix .       # lint
```

> Ruff is not a declared dependency; the VS Code extension uses its bundled binary. Run
> it from the CLI with `uvx ruff ...` if it is not installed in your environment.

### Database migrations

```bash
# After changing or adding a model (and importing it in migrations/env.py):
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
uv run alembic downgrade -1
```

Always review autogenerated migrations before applying them.

## Observability

- **Logs**: coloured console output in development/testing, single-line JSON on stdout in
  staging/production. Keys such as `password`, `token`, `secret` and `authorization` are
  redacted recursively before any handler sees them.
- **Traces**: FastAPI and SQLAlchemy are auto-instrumented. Set
  `OTEL_EXPORTER_OTLP_ENDPOINT` (e.g. `http://localhost:4318`) to export traces and logs
  to a collector; without it, telemetry stays local but trace IDs are still generated for
  log correlation.
- **Response headers**: `X-Request-ID` (trace ID) and `Server-Timing` on every response.

## License

[MIT](LICENSE)
