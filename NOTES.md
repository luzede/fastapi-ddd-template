## What was built

**Models** (`models.py`, `models.py`) — `user`, `session`, `account`, `verification`, `jwks`, `apikey`. `id`/`created_at`/`updated_at` and constraint naming come from `Base` (uuidv7, timestamptz, `pk_/uq_/fk_/ix_` names). `account`/`apikey`/`jwks`/`verification` match your DDL column-for-column; `user` and `session` are extended with proper FKs (`impersonated_by → user.id`) and `passive_deletes` cascades. I also fixed `Base.updated_at` to add `onupdate=func.now()` — `server_onupdate` alone only *declares* a DB trigger that doesn't exist.

**Endpoints** (45 operations under `/api/v1`), mirroring better-auth per the Context7 docs:

| Area | Routes |
|---|---|
| Core (`/auth`) | sign-up/in/out, get-session (with `set-auth-jwt`), list/revoke(-other/-all) sessions, verify-email, request/reset/change/set/verify-password |
| JWT plugin | `/token`, `/jwks` — EdDSA/Ed25519 default, private keys AES-GCM-encrypted with `AUTH__SECRET`, optional rotation + grace period, `kid` = row id |
| Admin plugin | create/list(search+filter+sort+offset)/get/update/delete user, set-role, set-password, ban/unban, list/revoke sessions, impersonate/stop-impersonating; default statements/roles reproduced, `admin_user_ids` supported |
| API key plugin | create (plaintext shown once, SHA-256 stored)/list/get/update/delete/verify; fixed-window rate limit, refill quota, expiry, permissions; `x-api-key` acts as a principal (`enableSessionForAPIKeys`) |
| Users | `/users/me` GET/PATCH/DELETE, change-email (verified → confirm from old inbox; unverified → immediate), accounts |

**Production hardening**: argon2id hashes with timing-equalised failed logins; HMAC-keyed single-use verification tokens; `SELECT … FOR UPDATE` on key verification so counters are exact under concurrency; ban checks on every request (revokes live sessions); fresh-session gate for sensitive actions; enumeration-safe reset/resend; RFC 9457 errors now carry a stable `code` and `WWW-Authenticate` on 401; CORS exposes `set-auth-token`/`set-auth-jwt`.

**Verification**: ran a 50-assertion end-to-end HTTP scenario (sign-up → JWT verified against JWKS → admin/impersonation/ban → API-key rate limiting → password/email/deletion flows) through the full middleware stack; all passed. Ruff clean; DDL compiled for PostgreSQL.

Two things to note:
- `LoggingMailer` is wired in `lifespan` as the email port — swap in a real provider before production.
- `.env.example` documents the new `AUTH__*` settings; `AUTH__SECRET` (≥32 chars) is required at startup.









The repo now follows one rule consistently:

**Files are singular when the module *is* one component; plural only when the module is a catalogue of many items. Folders are plural when they group sibling modules, singular when they represent one concept.**

| | Form | In this repo |
|---|---|---|
| Component file | singular | `router.py`, `repository.py`, `config.py`, `engine.py`, `session.py`, `mailer.py`, `security.py`, `access_control.py` |
| Catalogue file | plural | `models.py`, `schemas.py`, `exceptions.py`, `types.py`, `enums.py`, `handlers.py`, `dependencies.py`, `constants.py` |
| Grouping folder | plural | `modules/`, `services/`, `routers/`, `exceptions/` |
| Concept folder | singular | `core/`, `shared/`, `db/`, `middleware/` |

This is the convention used by FastAPI's own docs and the widely-copied Netflix Dispatch / `fastapi-best-practices` layouts, and it's what most of the repo already did — the inconsistencies were all in the auth module I added. Renamed:

- `auth/repositories.py` → `repository.py` (matches `users/repository.py`)
- `auth/services/sessions.py` → `session.py`
- `auth/services/api_keys.py` → `api_key.py`
- `auth/routers/api_keys.py` → `api_key.py`
- `auth/errors.py` → `constants.py` — it holds error *codes* (a `StrEnum`), not exception classes, so `errors` collided conceptually with `shared/exceptions/`

The apparent `router.py` vs `routers/` mismatch you noticed is actually the rule working as intended: `users/` has one router, so it's a file; `auth/` has four, so they live in a `routers/` package whose members are singular (`core.py`, `jwt.py`, `admin.py`, `api_key.py`).

All import sites updated, app builds with 45 operations, mappers configure, ruff clean.