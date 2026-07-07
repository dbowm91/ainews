# Milestone B.4: Environment and Documentation Alignment

## Objective

Make `.env.example`, README, deployment docs, configuration docs, and security docs match production runtime validation. A self-hosted operator should not have to infer which variables are required, which values must be hashed/random, or which provider settings are valid inside Docker.

## Current risk

Earlier review found drift between docs and runtime behavior. Examples:

- README quickstart mentions setting `SECRET_KEY` and at least one LLM provider, but production validation also requires a hashed `ADMIN_PASSWORD` and `CELERY_TASK_SECRET`.
- `CELERY_TASK_SECRET` appears under optional/advanced sections despite being production-required.
- Deployment docs contain stale or ambiguous auth examples.
- Docker, bare-metal, and provider config examples do not consistently explain path/network differences.

## Affected files

Expected files:

- `.env.example`
- `README.md`
- `docs/deployment.md`
- `docs/configuration.md`
- `docs/security.md`
- `docs/api.md` if API-token usage is documented
- `providers.yaml`
- `docker-compose.yml`
- `docker-compose.ollama.yml` or docs examples if added
- `AGENTS.md` and skill files if they include deployment guidance

## Required documentation model

Create one canonical production requirements table and reference it from other docs instead of duplicating divergent descriptions.

The canonical table should include:

| Variable/config | Required in production | Example | Generation command | Notes |
| --- | --- | --- | --- | --- |
| `SECRET_KEY` | yes | 64 hex chars | `python -c 'import secrets; print(secrets.token_hex(32))'` | Must match production validator |
| `ADMIN_PASSWORD` | yes | Werkzeug hash | `python scripts/hash_password.py` | Never plaintext |
| `CELERY_TASK_SECRET` | yes | random >=32 chars | `python -c 'import secrets; print(secrets.token_urlsafe(32))'` | Task signing/HMAC |
| `DATABASE_URL` | yes | SQLite default or external DB | n/a | Explain Docker volume path |
| `CELERY_BROKER_URL` | yes | Redis URL | n/a | Compose default available |
| `CELERY_RESULT_BACKEND` | yes | Redis URL | n/a | Compose default available |
| Provider config | yes | see providers examples | n/a | At least one enabled valid provider |
| `default_provider` | yes | provider ID | n/a | Must be enabled and valid |

Adjust exact variables to match code after Milestone B.1/B.2 implementation.

## Implementation plan

### Step 1: Make `.env.example` production-accurate

Move production-required values into a clear required section:

- `SECRET_KEY`
- `ADMIN_PASSWORD`
- `CELERY_TASK_SECRET`
- `FLASK_CONFIG=production`
- `DATABASE_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- provider/default-provider variables or pointer to provider config

Keep optional settings under optional sections only if runtime truly treats them as optional.

Add generation comments directly above secrets:

```bash
# Generate with: python -c 'import secrets; print(secrets.token_hex(32))'
SECRET_KEY=
```

```bash
# Generate hash with: python scripts/hash_password.py
ADMIN_PASSWORD=
```

```bash
# Generate with: python -c 'import secrets; print(secrets.token_urlsafe(32))'
CELERY_TASK_SECRET=
```

### Step 2: Update README quickstart

Docker quickstart should include a minimal ordered checklist:

1. Copy `.env.example`.
2. Generate `SECRET_KEY`.
3. Generate hashed `ADMIN_PASSWORD`.
4. Generate `CELERY_TASK_SECRET`.
5. Configure one valid provider and `default_provider`.
6. Start Compose.
7. Verify `/health`.
8. Log into admin.

Do not overload README with full provider docs; link to configuration/deployment docs for detail.

### Step 3: Update deployment docs

Fix stale or ambiguous examples:

- Replace HTTP Basic examples if the app does not support Basic auth for admin endpoints.
- Use API-token or session-auth examples where appropriate.
- Explain Docker database paths and volumes.
- Explain Redis requirements and defaults.
- Explain Celery worker/beat relationship.
- Include Docker/Ollama provider networking notes.
- Include migration command expectations.

### Step 4: Update configuration docs

Configuration docs should describe:

- Production versus development config behavior.
- Secret validation policy.
- Provider enablement/default-provider validation.
- Search provider config if relevant.
- Docker-specific provider host examples.
- How disabled providers with placeholder keys are treated.

### Step 5: Update security docs

Security docs should match final Milestone A/B behavior:

- Admin password must be hashed.
- API tokens store only verifiers.
- Session-auth mutating requests require CSRF.
- Verified bearer-token API requests bypass CSRF.
- Production startup fails closed on weak/missing secrets.
- `.env` permission checks in production.

### Step 6: Add docs consistency tests or checks

At minimum, add a lightweight test or script that checks key docs contain required production variable names. If overkill for now, add an explicit release checklist item.

Possible test:

```python
def test_env_example_lists_required_production_vars():
    text = Path(".env.example").read_text()
    for key in REQUIRED_PRODUCTION_ENV_KEYS:
        assert key in text
```

Possible script:

```bash
uv run python scripts/check_required_env_docs.py
```

### Step 7: Update agent guidance

If coding-agent instruction files exist, add concise guidance:

- Do not put production-required env vars under optional docs.
- Do not document `localhost` Ollama as Docker-default without caveats.
- Do not add enabled providers without validation tests.
- Keep README quickstart and `.env.example` aligned.

## Acceptance criteria

- `.env.example` clearly marks production-required settings.
- README quickstart names all required production secrets/config categories.
- Deployment docs no longer include stale Basic auth examples if unsupported.
- Provider examples match Docker/bare-metal network realities.
- Security docs match implemented auth/CSRF/API-token behavior.
- Docs and validation tests agree on required production settings.

## Handoff cautions

- Do not include real secrets or plausible-looking API keys in examples.
- Do not document weaker `SECRET_KEY` generation than runtime accepts.
- Do not recommend plaintext `ADMIN_PASSWORD` anywhere.
- Keep quickstart concise; put details in linked docs.
