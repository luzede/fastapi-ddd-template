# AGENTS.md

Guide for AI coding agents working in this repository. Read this first, then
[README.md](README.md) for the user-facing overview (setup, API, config).

## TL;DR

- Python **3.14**, managed with **uv**. Always run tools through `uv run …`.
- Async FastAPI + SQLAlchemy 2.0 (asyncpg) + PostgreSQL **18+**.
- Code is organised as **feature modules** under `app/modules/<name>/`; cross-cutting
  building blocks live in `app/shared/`; app wiring lives in `app/core/` and `app/main.py`.
- The definition of done is **`uv run pyrefly check` → 0 errors** (strict preset) plus
  Ruff-formatted code. There is **no test suite** yet (see [Current state](#current-state)).
- Errors are raised as `ProblemDetailException` subclasses, never `HTTPException`.
- The dev shell is usually **Windows PowerShell**: use `Copy-Item` rather than `cp`, and
  ignore the harmless "profile cannot be loaded" banner at the top of command output.

## Where to start

1. `app/main.py`: `create_app()` shows the whole wiring order (telemetry → logging →
   exception handlers → middleware → routers → OTel instrumentation).
2. `app/core/config.py`: every setting and how env vars map onto it.
3. `app/modules/auth/`: the most complete vertical slice (router → service → repository).
   Copy its shape when adding features.
4. `app/shared/exceptions/`: how errors are modelled and documented.
5. `git log --oneline -20`: recent intent. Commits are small and descriptive.

## Commands

```powershell
uv sync                                   # install deps into .venv
uv run python -m app.main                 # run server (reload on when ENVIRONMENT=development)
uv run pyrefly check                      # strict type check; must be 0 errors
uvx ruff format .                         # format (ruff is not a project dependency)
uvx ruff check --fix .                    # lint
uv run alembic revision --autogenerate -m "msg"   # new migration (needs a reachable DB)
uv run alembic upgrade head               # apply migrations
```

Quick smoke test that needs no database (lifespan doesn't run, so this works offline):

```powershell
uv run python -c "from app.main import create_app; print(list(create_app().openapi()['paths']))"
```

`create_app()` needs a valid `.env` (or env vars) because `DB__*` and `AUTH__*` fields are
required. Starting the real server requires a reachable PostgreSQL, because the lifespan
runs `SELECT 1` on startup.

## Architecture

```text
app/
├── main.py            create_app() factory + uvicorn entrypoint (main())
├── core/              config.py, lifespan.py (engine/session factory), logging.py, opentelemetry.py
├── shared/
│   ├── db/            base.py (Base: uuidv7 id, created_at, updated_at, naming convention)
│   │                  session.py (SessionDep: commit on success / rollback on error)
│   │                  repository.py (AsyncRepository[T]: get, list_page, create, update, delete…)
│   ├── exceptions/    exceptions.py (hierarchy), handlers.py, enums.py (ProblemType, ErrorCode),
│   │                  schemas.py (OpenAPI models), constants.py (PROBLEM_4xx/5xx response dicts)
│   ├── middleware/    TraceContextMiddleware (X-Request-ID), ServerTimingMiddleware
│   ├── utils/         small pure helpers
│   └── state.py       AppState / RequestState typing + AppStateDep
└── modules/
    ├── auth/          router, service (AuthService), security (JWT decode → JWTClaimsDep), schemas, types
    ├── user/          model (User), repository (UserRepository), dependencies (CurrentUserIdDep, CurrentUserDep)
    └── health/        /health/live, /health/ready
```

### Request flow and layering

```text
router.py  →  service.py  →  repository.py  →  SQLAlchemy AsyncSession
 (HTTP I/O,     (business      (queries only;      (one per request via SessionDep;
  schemas,       rules, raises   flush, never        committed by the dependency
  Depends)       Problem errs)   commit)             after the handler returns)
```

- **Routers** stay thin: parse input (Pydantic `schemas.py`), call a service, return a
  response model. Declare error responses with `responses={401: PROBLEM_401, …}`.
- **Services** hold business rules and raise domain errors (`BadRequestError`,
  `ConflictError`, …). They receive repositories through their constructor (keyword-only).
- **Repositories** subclass `AsyncRepository[Model]` and only add model-specific queries.
  They call `flush()`/`refresh()`, **never `commit()`**: the transaction boundary is
  `get_session` in `app/shared/db/session.py`.
- **Dependency providers** use one pattern everywhere:

  ```python
  async def get_widget_service(repo: WidgetRepositoryDep) -> WidgetService:
      return WidgetService(widgets=repo)


  type WidgetServiceDep = Annotated[WidgetService, Depends(get_widget_service)]
  ```

  Exception: `SessionDep` is a plain `Annotated` alias, not a `type` statement.
- **App state** (`db_engine`, `async_session_factory`, `started_at`) is created in
  `core/lifespan.py` and read through `AppStateDep`. Add new long-lived resources to
  `AppState` in `shared/state.py` and initialise/dispose them in the lifespan.

### Module dependencies

`auth` depends on `user` (model + repository), and `user.dependencies` depends on
`auth.security` (JWT claims). That's fine at package level, but keep it acyclic at file
level: `auth/security.py` must not import from `user`.

## Conventions

### Python and typing

- Target Python 3.14 syntax: PEP 695 generics (`class AsyncRepository[T: Base]`),
  `type X = …` aliases, `typing.override` on overridden methods, `X | None` unions.
- Pyrefly runs in the **strict** preset. Annotate everything; prefer `TypedDict`
  (`typing_extensions`, `closed=True` / `extra_items=`) for dict payloads over `dict[str, Any]`.
- Use `# type: ignore` only where a third-party signature forces it (as with the exception
  handler registrations), and keep it narrow.
- Put Pydantic I/O models in `schemas.py`, TypedDicts in `types.py`, SQLAlchemy models in
  `model.py`.
- Secrets in settings are `pydantic.Secret[str]`; call `.get_secret_value()` only at the
  point of use.
- Read settings through the cached accessors `get_settings()` / `get_auth_settings()`;
  don't instantiate `Settings()` directly.

### Comments and docstrings

- Module docstrings are one line describing the module's role.
- Comments explain **why** (RFC references, race conditions, library quirks), not what.
  Preserve existing explanatory comments when editing nearby code.

### Errors (RFC 9457)

- Raise a subclass from `app.shared.exceptions` (`ResourceNotFoundError`,
  `BadRequestError`, `ConflictError`, `AuthenticationError`, `PermissionError`,
  `RateLimitError`, `ServiceUnavailableError`, `InternalError`, `ValidationError`).
- Give business errors a stable `code=ErrorCode.X`. Add new codes to `ErrorCode` in
  `shared/exceptions/enums.py` under the matching problem-type section.
- New problem *types* need: a `ProblemType` member, an exception class, a Pydantic schema
  in `schemas.py`, a `PROBLEM_xxx` constant, and any new extension keys added to **both**
  TypedDicts in `shared/exceptions/types.py`.
- Never leak internals in `detail` for 5xx responses.

### Database

- All models inherit `app.shared.db.base.Base`, which provides `id` (UUIDv7, server-side),
  `created_at` and `updated_at`. Don't redeclare these.
- Constraint names come from `Base.metadata`'s naming convention; don't hand-name them.
- Use `select(exists().where(...))` for existence checks (see recent `perf(db)` commits)
  and keyset pagination via `AsyncRepository.list_page`, not OFFSET.
- Emails are normalised to lowercase in the repository queries and on create.

### Logging and observability

- Get loggers with `structlog.get_logger()` and log with key/value pairs:
  `log.info("user_signed_up", user_id=str(user.id))`.
- Sensitive keys (`password`, `token`, `secret`, `authorization`, …; see
  `SENSITIVE_KEYS` in `core/logging.py`) are redacted automatically, but don't log secrets
  deliberately anyway. Add new sensitive key names to that set.
- Request/access logging is intentionally off; OpenTelemetry spans cover it.
- CPU-heavy work (password hashing) goes through `asyncio.to_thread`.

### Git

- Conventional Commits with a scope: `feat(auth): …`, `fix(db): …`, `refactor(shared): …`,
  `perf(db): …`, `docs(shared): …`, `chore: …`. One logical change per commit.
- Never commit `.env`. `.env.example` is the documented source of truth for config. Update
  it whenever you add or change a setting.

## Recipes

### Add a new feature module

1. Create `app/modules/<name>/` with `__init__.py`, `model.py`, `repository.py`,
   `service.py`, `router.py`, `schemas.py` (+ `dependencies.py` / `types.py` if needed).
2. Model: subclass `Base`, set `__tablename__`.
3. Repository: `class XRepository(AsyncRepository[X])` with `get_x_repository(session: SessionDep)`
   and a `XRepositoryDep` alias.
4. Service: constructor takes repositories keyword-only; add `get_x_service` + `XServiceDep`.
5. Router: `APIRouter(prefix="/<name>", tags=["<name>"])`; protect routes with
   `CurrentUserIdDep` / `CurrentUserDep` from `app.modules.user.dependencies`.
6. Register the router in `register_routers()` in `app/main.py` (under `v1_router`).
7. **Import the model in `migrations/env.py`** and add it to the `models` tuple, or
   autogenerate won't see it.
8. Generate and review a migration, then run `uv run pyrefly check`.

### Add a setting

1. Add the field to the right group in `app/core/config.py` (with a default where sensible).
2. Document it in `.env.example` in the matching section (description, allowed values,
   default).

### Add an authenticated endpoint

Depend on `CurrentUserIdDep` (claims only, no DB hit) or `CurrentUserDep` (loads the `User`,
404 if deleted). Add `401: PROBLEM_401` to `responses`.

## Gotchas

- **Middleware order is reversed**: the last `add_middleware` call runs first. CORS must
  stay outermost (see comments in `register_middlewares`).
- **OpenTelemetry setup is a module-level singleton** (`core/opentelemetry.py`), not
  `lru_cache`, because OTel's global providers are write-once. Don't "simplify" it.
- `SQLAlchemyInstrumentor` must be given `engine.sync_engine`.
- `get_session` commits **after** the handler returns. A unique-constraint violation can
  surface at commit time unless the repository flushes, which is why `create()` flushes and
  the auth service catches `IntegrityError` around it.
- Alembic builds its URL from app settings in `migrations/env.py` and escapes `%` for
  configparser. The `sqlalchemy.url` in `alembic.ini` is an unused placeholder.
- `uuidv7()` is a PostgreSQL 18 built-in. Older Postgres will fail the first migration.
- `.env.example` is production-flavoured (`ENVIRONMENT=production`, `SERVER__HOST=0.0.0.0`).
  Switch to `development` locally or `/docs` will be disabled.
- `main()` disables Uvicorn's log config and access log on purpose; logging is owned by
  `setup_logging`.

## Current state

Snapshot as of the last update of this file. Verify with `git status` / `git log`.

**Implemented**: settings, lifespan, structured logging + redaction, OTel traces/logs,
RFC 9457 error system with OpenAPI docs, trace/timing middleware, health probes, `User`
model + initial migration, email/password sign-up, OAuth2 password login, change
password, JWT issue/verify with a `roles` claim.

**Uncommitted / in progress** (check `git status`):
- `migrations/versions/0001_534587eb6ad4_.py`: initial `user` table migration, untracked.
- `app/shared/utils/text_processing.py` (`strip_and_lower`): new helper, not used yet
  (likely meant to replace the inline `email.lower()` calls).
- `app/modules/auth/utils.py` and `app/modules/user/types.py`: empty placeholders.

**Known gaps / candidate next tasks**:
- **No tests.** pytest was deliberately removed from dev deps; `httpx` remains for a
  future `AsyncClient`-based suite. Agree on the approach with the user before adding one.
- No Ruff config in `pyproject.toml` (defaults apply); no CI, Dockerfile or docker-compose.
- `AuthService.verify_password` raises `BadRequestError("Invalid password")` without an
  `ErrorCode`.
- Roles exist in the JWT, but there's no authorization dependency yet (e.g.
  `require_role(...)` raising `PermissionError`). `RateLimitError` / `PROBLEM_429` exist but
  nothing produces them.
- `AuthSettings.secret` is validated but currently unused. Its docstring anticipates key
  encryption and verification tokens. `ErrorCode.INVALID_TOKEN` and
  `user/schemas.py:UserCreate` are also unused.
- Some docstrings mention "better-auth" routes and plugins (jwt/admin/apikey). That's the
  target API surface the auth module is modelled on, not something that's implemented yet.
- `pyproject.toml` still has the placeholder description, and `ProblemType` URIs use
  `https://api.example.com/problems`.

Update this section when you finish a task so the next agent starts from an accurate
picture.

## Before you finish

- [ ] `uv run pyrefly check` reports 0 errors.
- [ ] Code is Ruff-formatted, with imports sorted.
- [ ] New settings are documented in `.env.example`; new models are imported in `migrations/env.py`.
- [ ] New error cases use `ProblemDetailException` subclasses with an `ErrorCode`, and the
      route's `responses=` lists them.
- [ ] README updated if you changed setup, endpoints or configuration; "Current state"
      above updated.

